from dataclasses import Field, dataclass, is_dataclass
from enum import Enum
from functools import wraps
from itertools import chain
from typing import (
    AbstractSet,
    Any,
    Callable,
    Collection,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema import settings
from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.conversions import (
    Conversions,
    handle_container_conversions,
)
from apischema.conversions.utils import (
    Converter,
    identity,
)
from apischema.conversions.visitor import Deserialization, DeserializationVisitor
from apischema.dataclass_utils import (
    get_alias,
    get_default,
    get_field_conversions,
    get_fields,
    get_requirements,
    has_default,
    is_required,
)
from apischema.dataclasses import replace
from apischema.dependent_required import DependentRequired
from apischema.deserialization.coercion import Coercion, get_coercer
from apischema.deserialization.merged import get_init_merged_alias
from apischema.json_schema.constraints import (
    ArrayConstraints,
    Constraints,
    merge_constraints,
)
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.schema import Schema, get_schema
from apischema.metadata.implem import ValidatorsMetadata
from apischema.metadata.keys import (
    DEFAULT_FALLBACK_METADATA,
    MERGED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    SCHEMA_METADATA,
    SKIP_METADATA,
    VALIDATORS_METADATA,
    check_metadata,
    is_aggregate_field,
)
from apischema.skip import filter_skipped
from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    NoneType,
    OrderedDict,
)
from apischema.typing import get_origin
from apischema.utils import get_origin_or_type, opt_or
from apischema.validation.errors import (
    ErrorKey,
    ValidationError,
    apply_aliaser,
    merge_errors,
)
from apischema.validation.mock import ValidatorMock
from apischema.validation.validator import (
    Validator,
    get_validators,
    validate,
)
from apischema.visitor import Unsupported

DICT_TYPE = get_origin(Dict[Any, Any])
LIST_TYPE = get_origin(List[Any])

MISSING_PROPERTY = ValidationError(["missing property"])
UNEXPECTED_PROPERTY = ValidationError(["unexpected property"])

T = TypeVar("T")


# TODO maybe ctx parameters to deserializers
@dataclass
class DeserializationContext:
    additional_properties: bool
    coercion: Coercion
    default_fallback: bool

    def __post_init__(self):
        self.coercer = get_coercer(self.coercion)

    def merge(
        self,
        additional_properties: bool = None,
        coercion: Coercion = None,
        default_fallback: bool = None,
    ) -> "DeserializationContext":
        if any(
            arg is not None
            for arg in (additional_properties, coercion, default_fallback)
        ):
            return replace(
                self,
                additional_properties=opt_or(
                    additional_properties, self.additional_properties
                ),
                coercion=opt_or(coercion, self.coercion),
                default_fallback=opt_or(default_fallback, self.default_fallback),
            )
        else:
            return self


def get_constraints(tp: AnyType) -> Optional[Constraints]:
    schema = get_schema(tp)
    return schema.constraints if schema is not None else None


DeserializationMethod = Callable[[DeserializationContext, Any], Any]
Factory = Callable[[Optional[Constraints], Sequence[Validator]], DeserializationMethod]


@dataclass(frozen=True)
class DeserializationMethodFactory:
    factory: Factory
    constraints: Optional[Constraints] = None
    validators: Sequence[Validator] = ()

    @property
    def method(self) -> DeserializationMethod:
        return self.factory(self.constraints, self.validators)  # type: ignore

    @staticmethod
    def from_type(tp: AnyType) -> Callable[[Factory], "DeserializationMethodFactory"]:
        return lambda factory: DeserializationMethodFactory(
            factory, get_constraints(tp), get_validators(tp)
        )

    def merge(
        self,
        constraints: Optional[Constraints] = None,
        validators: Sequence[Validator] = (),
    ) -> "DeserializationMethodFactory":
        if constraints is None and not validators:
            return self
        return replace(
            self,
            constraints=merge_constraints(self.constraints, constraints),
            validators=(*self.validators, *validators),
        )


class RecDeserializerMethodFactory:
    def __init__(self):
        self._ref: Optional[DeserializationMethodFactory] = None
        self._constraints: Optional[Constraints] = None
        self._validators: Sequence[Validator] = ()
        self._children: List[RecDeserializerMethodFactory] = []
        self._method: Optional[DeserializationMethod] = None

    def __hash__(self):
        return object.__hash__(self)

    def set_ref(
        self, factory: DeserializationMethodFactory
    ) -> DeserializationMethodFactory:
        self._ref = factory.merge(self._constraints, self._validators)
        for child in self._children:
            child.set_ref(factory)
        return factory

    def merge(
        self,
        constraints: Optional[Constraints] = None,
        validators: Sequence[Validator] = (),
    ) -> "RecDeserializerMethodFactory":
        child = RecDeserializerMethodFactory()
        if self._ref is not None:
            child._ref = self._ref.merge(constraints, validators)
        else:
            child._constraints = merge_constraints(self._constraints, constraints)
            child._validators = (*self._validators, *validators)
        self._children.append(child)
        return child

    @property  # type: ignore
    def method(self) -> DeserializationMethod:
        if self._method is None:

            def method(ctx: DeserializationContext, data: Any) -> Any:
                if self._method is None:
                    assert self._ref is not None
                    self._method = self._ref.method
                return self._method(ctx, data)

            return method
        else:
            return self._method


FieldDeserializer = Callable[
    [
        DeserializationContext,
        Any,
        Dict[str, Any],
        List[str],
        Dict[ErrorKey, ValidationError],
    ],
    None,
]


def field_deserializer(
    field: Field, method: DeserializationMethod, aliaser: Aliaser
) -> FieldDeserializer:
    name = field.name
    alias = aliaser(get_alias(field))
    aggregate = is_aggregate_field(field)
    default = has_default(field)
    default_fallback = DEFAULT_FALLBACK_METADATA in field.metadata

    def deserializer(
        ctx: DeserializationContext,
        data: Any,
        values: Dict[str, Any],
        errors: List[str],
        field_errors: Dict[ErrorKey, ValidationError],
    ):
        try:
            values[name] = method(ctx, data)  # type: ignore
        except ValidationError as err:
            if default and (default_fallback or ctx.default_fallback):
                pass
            elif aggregate:
                errors.extend(err.messages)
                field_errors.update(err.children)
            else:
                field_errors[alias] = err

    return deserializer


def with_validators(
    validators: Sequence[Validator],
) -> Callable[[DeserializationMethod], DeserializationMethod]:
    if not validators:
        return lambda method: method

    def decorator(method: DeserializationMethod) -> DeserializationMethod:
        @wraps(method)
        def wrapper(ctx: DeserializationContext, data: Any) -> Any:
            return validate(method(ctx, data), validators)

        return wrapper

    return decorator


class DeserializationMethodVisitor(
    DeserializationVisitor[DeserializationMethodFactory]
):
    def __init__(self, aliaser: Aliaser):
        super().__init__()
        self._rec_sentinel: Dict[Any, RecDeserializerMethodFactory] = {}
        self.aliaser = aliaser

    def _visit(self, tp: AnyType) -> DeserializationMethodFactory:
        key = self._generic or tp, self._conversions
        if key in self._rec_sentinel:
            return cast(DeserializationMethodFactory, self._rec_sentinel[key])
        else:
            self._rec_sentinel[key] = RecDeserializerMethodFactory()
            factory = super()._visit(tp)
            return self._rec_sentinel.pop(key).set_ref(factory)

    def method(self, cls) -> DeserializationMethod:
        return self.visit(cls).method

    def annotated(
        self, tp: AnyType, annotations: Sequence[Any]
    ) -> DeserializationMethodFactory:
        factory = self.visit(tp)
        for annotation in reversed(annotations):
            if isinstance(annotation, Mapping):
                if SCHEMA_METADATA in annotation:
                    schema: Schema = annotation[SCHEMA_METADATA]
                    factory = factory.merge(constraints=schema.constraints)
                if VALIDATORS_METADATA in annotation:
                    validators: ValidatorsMetadata = annotation[VALIDATORS_METADATA]
                    factory = factory.merge(validators=validators.validators)
        return factory

    def any(self) -> DeserializationMethodFactory:
        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                return data if constraints is None else constraints.validate(data)

            return method

        return factory

    def collection(
        self, cls: Type[Iterable], value_type: AnyType
    ) -> DeserializationMethodFactory:
        deserialize_value = self.method(value_type)

        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(list, data)
                elts = []
                elt_errors: Dict[ErrorKey, ValidationError] = {}
                for i, elt in enumerate(data):
                    try:
                        elts.append(deserialize_value(ctx, elt))
                    except ValidationError as err:
                        elt_errors[i] = err
                errors = () if constraints is None else constraints.errors(data)
                if elt_errors or errors:
                    raise ValidationError(errors, elt_errors)
                return elts if cls is LIST_TYPE else COLLECTION_TYPES[cls](elts)

            return method

        return factory

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> DeserializationMethodFactory:
        assert is_dataclass(cls)
        normal_fields: List[
            Tuple[str, FieldDeserializer, Union[bool, AbstractSet[str]]]
        ] = []
        merged_fields: List[Tuple[AbstractSet[str], FieldDeserializer]] = []
        pattern_fields: List[Tuple[Pattern, FieldDeserializer]] = []
        additional_field: Optional[FieldDeserializer] = None
        post_init_modified = {
            field.name
            for field in chain(fields, init_vars)
            if POST_INIT_METADATA in field.metadata
        }
        defaults: Dict[str, Callable[[], Any]] = {}
        required_by = get_requirements(
            cls, DependentRequired.required_by, self.operation
        )
        for field in get_fields(fields, init_vars, self.operation):  # noqa: F402
            metadata = check_metadata(field)
            if SKIP_METADATA in metadata or not field.init:
                continue
            if has_default(field):
                defaults[field.name] = lambda: get_default(field)
            field_type = types[field.name]
            field_factory = self.visit_with_conversions(
                field_type, get_field_conversions(field, self.operation)
            )
            if SCHEMA_METADATA in metadata:
                field_factory = field_factory.merge(
                    constraints=metadata[SCHEMA_METADATA].constraints
                )
            if VALIDATORS_METADATA in metadata:
                field_factory = field_factory.merge(
                    validators=metadata[VALIDATORS_METADATA].validators
                )
            deserializer = field_deserializer(field, field_factory.method, self.aliaser)
            if MERGED_METADATA in metadata:
                merged_alias = get_init_merged_alias(cls, field, field_type)
                merged_fields.append(
                    (set(map(self.aliaser, merged_alias)), deserializer)
                )
            elif PROPERTIES_METADATA in metadata:
                pattern = metadata[PROPERTIES_METADATA]
                if pattern is None:
                    additional_field = deserializer
                elif pattern is ...:
                    pattern_fields.append((infer_pattern(field_type), deserializer))
                else:
                    pattern_fields.append((pattern, deserializer))
            else:
                required = is_required(field) or {
                    self.aliaser(get_alias(req)) for req in required_by.get(field) or ()
                }
                normal_fields.append(
                    (self.aliaser(get_alias(field)), deserializer, required)
                )

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(dict, data)
                values: Dict[str, Any] = {}
                aliases: List[str] = []
                errors = [] if constraints is None else constraints.errors(data)
                field_errors: Dict[ErrorKey, ValidationError] = OrderedDict()

                for alias, deserialize_field, required in normal_fields:
                    if alias in data:
                        aliases.append(alias)
                        deserialize_field(
                            ctx, data[alias], values, errors, field_errors
                        )
                    elif not required:
                        pass
                    elif required is True:
                        field_errors[alias] = MISSING_PROPERTY
                    else:
                        assert isinstance(required, AbstractSet)
                        requiring = required & data.keys()
                        if requiring:
                            msg = f"missing property (required by {sorted(requiring)})"
                            field_errors[alias] = ValidationError([msg])

                for merged_alias, deserialize_field in merged_fields:
                    merged = {
                        alias: data[alias] for alias in merged_alias if alias in data
                    }
                    aliases.extend(merged)
                    deserialize_field(ctx, merged, values, errors, field_errors)
                if len(data) != len(aliases):
                    remain = data.keys() - set(aliases)
                    for pattern, deserialize_field in pattern_fields:
                        matched = {
                            key: data[key] for key in remain if pattern.match(key)
                        }
                        remain -= matched.keys()
                        deserialize_field(ctx, matched, values, errors, field_errors)
                    if additional_field is not None:
                        additional = {key: data[key] for key in remain}
                        additional_field(ctx, additional, values, errors, field_errors)
                    elif remain and not ctx.additional_properties:
                        for key in remain:
                            field_errors[key] = UNEXPECTED_PROPERTY
                else:
                    for _, deserialize_field in pattern_fields:
                        deserialize_field(ctx, {}, values, errors, field_errors)
                    if additional_field is not None:
                        additional_field(ctx, {}, values, errors, field_errors)
                validators2: Sequence[Validator]
                if validators:
                    init: Dict[str, Any] = {}
                    for init_field in init_vars:
                        if init_field.name in values:
                            init[init_field.name] = values[init_field.name]
                        if (
                            init_field.name not in field_errors
                            and init_field.name in defaults
                        ):
                            init[init_field.name] = defaults[init_field.name]()
                    # Don't keep validators when all dependencies are default
                    validators2 = [
                        v for v in validators if v.dependencies & values.keys()
                    ]
                    if field_errors or errors:
                        error = ValidationError(errors, field_errors)
                        invalid_fields = field_errors.keys() | post_init_modified
                        validators2 = [
                            v
                            for v in validators2
                            if not v.dependencies & invalid_fields
                        ]
                        try:
                            validate(ValidatorMock(cls, values), validators2, **init)
                        except ValidationError as err:
                            error = merge_errors(
                                error, apply_aliaser(err, self.aliaser)
                            )
                        raise error
                elif field_errors or errors:
                    raise ValidationError(errors, field_errors)
                else:
                    validators2, init = ..., ...  # type: ignore # only for linter
                try:
                    res = cls(**values)
                except AssertionError:
                    raise
                except ValidationError as err:
                    raise apply_aliaser(err, self.aliaser)
                except TypeError as err:
                    if str(err).startswith("__init__() got"):
                        raise Unsupported(cls)
                    else:
                        raise ValidationError([str(err)])
                except Exception as err:
                    raise ValidationError([str(err)])
                try:
                    return validate(res, validators2, **init) if validators else res
                except ValidationError as err:
                    raise apply_aliaser(err, self.aliaser)

            return method

        return factory

    def enum(self, cls: Type[Enum]) -> DeserializationMethodFactory:
        deserialize_literal = self.literal([elt.value for elt in cls]).method

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                try:
                    result = cls(data)
                except ValueError:
                    result = cls(deserialize_literal(ctx, data))
                if constraints is not None:
                    constraints.validate(data)
                return result

            return method

        return factory

    def literal(self, values: Sequence[Any]) -> DeserializationMethodFactory:
        values_deserializers = [(value, self.method(type(value))) for value in values]

        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                if data in values:
                    result = data
                else:
                    for value, deserialize_value in values_deserializers:
                        try:
                            # Literal can contain Enum values which has to be visited
                            if (
                                deserialize_value(ctx, ctx.coercer(type(value), data))
                                == value
                            ):
                                result = value
                                break
                        except Exception:
                            continue
                    else:
                        allowed_values = [
                            value if not isinstance(value, Enum) else value.value
                            for value in values
                        ]
                        raise ValidationError([f"not one of {allowed_values}"])
                if constraints is not None:
                    constraints.validate(result)
                return result

            return method

        return factory

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> DeserializationMethodFactory:
        deserialize_key = self.method(key_type)
        deserialize_value = self.method(value_type)

        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(dict, data)
                items = {}
                item_errors: Dict[ErrorKey, ValidationError] = {}
                for key, value in data.items():
                    assert isinstance(key, str)
                    try:
                        items[deserialize_key(ctx, key)] = deserialize_value(ctx, value)
                    except ValidationError as err:
                        item_errors[key] = err
                errors = () if constraints is None else constraints.errors(data)
                if item_errors or errors:
                    raise ValidationError(errors, item_errors)
                return items if cls is DICT_TYPE else MAPPING_TYPES[cls](items)

            return method

        return factory

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> DeserializationMethodFactory:
        items_deserializers = [
            (key, self.aliaser(key), self.method(tp)) for key, tp in types.items()
        ]

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(dict, data)
                items: Dict[str, Any] = {}
                item_errors: Dict[ErrorKey, ValidationError] = {}
                for key, alias, deserialize_item in items_deserializers:
                    if key in data:
                        try:
                            items[key] = deserialize_item(ctx, data[alias])
                        except ValidationError as err:
                            if key not in defaults or not ctx.default_fallback:
                                item_errors[alias] = err
                    elif key not in defaults:
                        item_errors[alias] = MISSING_PROPERTY

                if not ctx.additional_properties:
                    for key in sorted(data.keys() - defaults.keys() - items.keys()):
                        item_errors[key] = UNEXPECTED_PROPERTY
                errors = () if constraints is None else constraints.errors(data)
                if item_errors or errors:
                    raise ValidationError(errors, item_errors)
                return cls(**items)

            return method

        return factory

    def new_type(
        self, tp: AnyType, super_type: AnyType
    ) -> DeserializationMethodFactory:
        return self.visit(super_type).merge(get_constraints(tp), get_validators(tp))

    def primitive(self, cls: Type) -> DeserializationMethodFactory:
        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            if constraints is None:
                method = lambda ctx, data: ctx.coercer(cls, data)  # noqa: E731
            else:

                def method(ctx: DeserializationContext, data: Any) -> Any:
                    data = ctx.coercer(cls, data)
                    if constraints is not None and data is not None:
                        constraints.validate(data)
                    return data

            return with_validators(validators)(method)

        return factory

    def subprimitive(self, cls: Type, superclass: Type) -> DeserializationMethodFactory:
        super_factory = self.primitive(superclass)

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            method = super_factory.merge(constraints, validators).method
            return lambda ctx, data: cls(method(ctx, data))

        return factory

    def tuple(self, types: Sequence[AnyType]) -> DeserializationMethodFactory:
        tuple_constraints = ArrayConstraints(min_items=len(types), max_items=len(types))
        elts_deserializers = [self.method(cls) for cls in types]

        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(list, data)
                if len(data) != len(types):
                    tuple_constraints.validate(data)
                elts: List[Any] = []
                elt_errors: Dict[ErrorKey, ValidationError] = {}
                for i, (deserialize_elt, elt) in enumerate(
                    zip(elts_deserializers, data)
                ):
                    try:
                        elts.append(deserialize_elt(ctx, elt))
                    except ValidationError as err:
                        elt_errors[i] = err
                errors = () if constraints is None else constraints.errors(data)
                if elt_errors or errors:
                    raise ValidationError(errors, elt_errors)
                return tuple(elts)

            return method

        return factory

    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool
    ) -> DeserializationMethodFactory:
        items_deserializers = {key: self.method(tp) for key, tp in keys.items()}

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(dict, data)
                items: Dict[str, Any] = {}
                key_count = 0
                item_errors: Dict[ErrorKey, ValidationError] = {}
                for key, value in data.items():
                    if key in items_deserializers:
                        key_count += 1
                        try:
                            items[key] = items_deserializers[key](ctx, value)
                        except ValidationError as err:
                            item_errors[key] = err
                    else:
                        items[key] = value
                if total and key_count != len(keys):
                    for key in keys:
                        if key not in data:
                            item_errors[key] = MISSING_PROPERTY
                errors = () if constraints is None else constraints.errors(data)
                if item_errors or errors:
                    raise ValidationError(errors, item_errors)
                return items

            return method

        return factory

    def union(self, alternatives: Sequence[AnyType]) -> DeserializationMethodFactory:
        factories = [self.visit(cls) for cls in filter_skipped(alternatives)]
        optional = NoneType in alternatives

        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            alt_deserializers = [
                fact.merge(constraints, validators).method for fact in factories
            ]

            def method(ctx: DeserializationContext, data: Any) -> Any:
                # Optional optimization
                if data is None and optional:
                    return None
                error: Optional[ValidationError] = None
                for deserialize_alt in alt_deserializers:
                    try:
                        return deserialize_alt(ctx, data)
                    except ValidationError as err:
                        error = merge_errors(error, err)
                else:
                    if error is None:  # empty union
                        return data
                    else:
                        raise error

            return method

        return factory

    def visit_conversion(
        self, tp: AnyType, conversion: Deserialization, dynamic: bool
    ) -> DeserializationMethodFactory:
        assert conversion
        cls = get_origin_or_type(tp)
        factories = [
            (
                self.visit_with_conversions(
                    self._update_generic_args(tp, conv),
                    handle_container_conversions(
                        conv.source, conv.sub_conversions, self._conversions, dynamic
                    ),
                ),
                cast(Converter, conv.converter),
                (conv.additional_properties, conv.coercion, conv.default_fallback),
            )
            for conv in conversion
        ]

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            alt_deserializers = [
                (fact.merge(constraints, validators).method, converter, conv_ctx)
                for fact, converter, conv_ctx in factories
            ]
            if len(alt_deserializers) == 1:
                deserialize_alt, converter, conv_ctx = alt_deserializers[0]
                if converter is identity:
                    method = deserialize_alt
                else:

                    def method(ctx: DeserializationContext, data: Any) -> Any:
                        try:
                            return converter(
                                deserialize_alt(ctx.merge(*conv_ctx), data)
                            )
                        except (ValidationError, AssertionError):
                            raise
                        except Exception as err:
                            raise ValidationError([str(err)])

            else:

                def method(ctx: DeserializationContext, data: Any) -> Any:
                    error: Optional[ValidationError] = None
                    for deserialize_alt, converter, conv_ctx in alt_deserializers:
                        try:
                            value = deserialize_alt(ctx.merge(*conv_ctx), data)
                            break
                        except ValidationError as err:
                            error = merge_errors(error, err)
                    else:
                        assert error is not None
                        raise error
                    try:
                        return converter(value)
                    except (ValidationError, AssertionError):
                        raise
                    except Exception as err:
                        raise ValidationError([str(err)])

            return method

        return factory


@cache
def get_method(
    tp: AnyType, conversions: Optional[Conversions], aliaser: Aliaser
) -> DeserializationMethod:
    factory = DeserializationMethodVisitor(aliaser).visit_with_conversions(
        tp, conversions
    )
    return factory.method


@overload
def deserialize(
    tp: Type[T],
    data: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
    additional_properties: bool = None,
    coercion: Coercion = None,
    default_fallback: bool = None,
) -> T:
    ...


@overload
def deserialize(
    tp: AnyType,
    data: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
    additional_properties: bool = None,
    coercion: Coercion = None,
    default_fallback: bool = None,
) -> Any:
    ...


def deserialize(
    tp: AnyType,
    data: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
    additional_properties: bool = None,
    coercion: Coercion = None,
    default_fallback: bool = None,
):
    if additional_properties is None:
        additional_properties = settings.additional_properties
    if coercion is None:
        coercion = settings.coercion
    if default_fallback is None:
        default_fallback = settings.default_fallback
    if aliaser is None:
        aliaser = settings.aliaser()
    ctx = DeserializationContext(additional_properties, coercion, default_fallback)
    if isinstance(conversions, Collection):
        conversions = tuple(conversions)  # Make it hashable
    return get_method(tp, conversions, aliaser)(ctx, data)
