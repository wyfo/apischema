from dataclasses import Field, dataclass, field, replace
from enum import Enum
from functools import wraps
from itertools import chain
from typing import (
    AbstractSet,
    Any,
    Callable,
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
    cast,
    overload,
)

from apischema import settings
from apischema.cache import cache
from apischema.conversions.metadata import get_field_conversions
from apischema.conversions.utils import Conversions, ConversionsWrapper
from apischema.conversions.visitor import Deserialization, DeserializationVisitor
from apischema.dataclass_utils import (
    get_alias,
    get_all_fields,
    get_default,
    get_init_merged_alias,
    get_required_by,
    has_default,
    is_required,
)
from apischema.coercion import Coercion, get_coercer
from apischema.json_schema.constraints import (
    ArrayConstraints,
    Constraints,
    merge_constraints,
)
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.schema import Schema, get_schema
from apischema.metadata.keys import (
    DEFAULT_FALLBACK_METADATA,
    MERGED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    SCHEMA_METADATA,
    SKIP_METADATA,
    VALIDATORS_METADATA,
    check_metadata,
)
from apischema.skip import filter_skipped
from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    DICT_TYPE,
    LIST_TYPE,
    MAPPING_TYPES,
    NoneType,
    OrderedDict,
)
from apischema.validation.errors import ErrorKey, ValidationError, merge_errors
from apischema.validation.mock import ValidatorMock
from apischema.validation.validator import (
    Validator,
    ValidatorsMetadata,
    get_validators,
    validate,
)
from apischema.visitor import Unsupported

T = TypeVar("T")


@dataclass
class DeserializationContext:
    additional_properties: bool = field(
        default_factory=lambda: settings.additional_properties
    )
    coercion: Coercion = field(default_factory=lambda: settings.coercion)
    default_fallback: bool = field(default_factory=lambda: settings.default_fallback)

    def __post_init__(self):
        self.coercer = get_coercer(self.coercion)


def get_constraints(cls: AnyType) -> Optional[Constraints]:
    schema = get_schema(cls)
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
    def from_type(cls: AnyType) -> Callable[[Factory], "DeserializationMethodFactory"]:
        return lambda factory: DeserializationMethodFactory(
            factory, get_constraints(cls), get_validators(cls)
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


@dataclass(frozen=True)
class DeserializationField:
    name: str
    required: bool
    default: bool
    default_fallback: bool
    method: DeserializationMethod

    def deserialize(
        self,
        ctx: DeserializationContext,
        data: Any,
        values: Dict[str, Any],
        errors: List[str],
        field_errors: Dict[ErrorKey, ValidationError],
        alias: str = None,
    ):
        try:
            values[self.name] = self.method(ctx, data)  # type: ignore
        except ValidationError as err:
            if self.default and (self.default_fallback or ctx.default_fallback):
                pass
            elif alias is not None:
                field_errors[alias] = err
            else:
                errors.extend(err.messages)
                field_errors.update(err.children)


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
    def __init__(self, conversions: Optional[Conversions]):
        super().__init__(conversions)
        self._rec_sentinel: Dict[Any, RecDeserializerMethodFactory] = {}

    def visit_not_builtin(self, cls: AnyType) -> DeserializationMethodFactory:
        key = self._type_vars.specialize(cls), id(self.conversions)
        if key in self._rec_sentinel:
            return cast(DeserializationMethodFactory, self._rec_sentinel[key])
        else:
            self._rec_sentinel[key] = RecDeserializerMethodFactory()
            factory = super().visit_not_builtin(cls)
            return self._rec_sentinel.pop(key).set_ref(factory)

    def method(self, cls) -> DeserializationMethod:
        return self.visit(cls).method

    def annotated(
        self, cls: AnyType, annotations: Sequence[Any]
    ) -> DeserializationMethodFactory:
        factory = self.visit(cls)
        for annotation in reversed(annotations):
            if isinstance(annotation, Schema):
                factory = factory.merge(constraints=annotation.constraints)
            if isinstance(annotation, ValidatorsMetadata):
                factory = factory.merge(validators=annotation.validators)

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
        normal_fields: List[Tuple[str, DeserializationField]] = []
        merged_fields: List[Tuple[AbstractSet[str], DeserializationField]] = []
        pattern_fields: List[Tuple[Pattern, DeserializationField]] = []
        additional_field: Optional[DeserializationField] = None
        post_init_modified_fields = {
            f.name
            for f in get_all_fields(cls).values()
            if POST_INIT_METADATA in f.metadata
        }
        defaults: Dict[str, Callable[[], Any]] = {}
        required_by, _ = get_required_by(cls)
        for field in chain(fields, init_vars):  # noqa F402
            metadata = check_metadata(field)
            if SKIP_METADATA in metadata or not field.init:
                continue
            field_type = types[field.name]
            if has_default(field):
                defaults[field.name] = lambda: get_default(field)
            conversions = get_field_conversions(field, field_type)
            if conversions is None:
                field_factory = self.visit(field_type)
            elif conversions.deserializer is None:
                with self._replace_conversions(conversions.deserialization):
                    field_factory = self.visit(field_type)
            else:
                field_factory = self.visit_conversion(
                    field_type, conversions.deserialization_conversion(field_type)
                )
            if SCHEMA_METADATA in metadata:
                field_factory = field_factory.merge(
                    constraints=metadata[SCHEMA_METADATA].constraints
                )
            if VALIDATORS_METADATA in metadata:
                field_factory = field_factory.merge(
                    validators=metadata[VALIDATORS_METADATA].validators
                )
            field2 = DeserializationField(
                field.name,
                is_required(field),
                has_default(field),
                DEFAULT_FALLBACK_METADATA in metadata,
                field_factory.method,
            )
            if MERGED_METADATA in metadata:
                merged_fields.append((get_init_merged_alias(field_type), field2))
            elif PROPERTIES_METADATA in metadata:
                pattern = metadata[PROPERTIES_METADATA]
                if pattern is None:
                    additional_field = field2
                elif pattern is ...:
                    pattern_fields.append((infer_pattern(field_type), field2))
                else:
                    pattern_fields.append((pattern, field2))
            else:
                normal_fields.append((get_alias(field), field2))

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

                for alias, field in normal_fields:
                    if alias in data:
                        aliases.append(alias)
                        field.deserialize(
                            ctx, data[alias], values, errors, field_errors, alias
                        )
                    else:
                        if field.name in required_by:
                            requiring = required_by[field.name] & data.keys()
                            if requiring:
                                req = sorted(requiring)
                                msg = f"missing property (required by {req})"
                                field_errors[alias] = ValidationError([msg])
                        if field.required and alias not in field_errors:
                            field_errors[alias] = ValidationError(["missing property"])
                for merged_alias, field in merged_fields:
                    merged = {
                        alias: data[alias] for alias in merged_alias if alias in data
                    }
                    aliases.extend(merged)
                    field.deserialize(ctx, merged, values, errors, field_errors)
                if len(data) != len(aliases):
                    remain = data.keys() - set(aliases)
                    for pattern, field in pattern_fields:
                        matched = {
                            key: data[key] for key in remain if pattern.match(key)
                        }
                        remain -= matched.keys()
                        field.deserialize(ctx, matched, values, errors, field_errors)
                    if additional_field is not None:
                        additional = {key: data[key] for key in remain}
                        additional_field.deserialize(
                            ctx, additional, values, errors, field_errors
                        )
                    elif remain and not ctx.additional_properties:
                        for key in remain:
                            field_errors[key] = ValidationError(["unexpected property"])
                else:
                    for _, field in pattern_fields:
                        field.deserialize(ctx, {}, values, errors, field_errors)
                    if additional_field is not None:
                        additional_field.deserialize(
                            ctx, {}, values, errors, field_errors
                        )
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
                        invalid_fields = field_errors.keys() | post_init_modified_fields
                        validators2 = [
                            v
                            for v in validators2
                            if not v.dependencies & invalid_fields
                        ]
                        try:
                            validate(ValidatorMock(cls, values), validators2, **init)
                        except ValidationError as err:
                            error = merge_errors(error, err)
                        raise error
                else:
                    validators2, init = ..., ...  # type: ignore # only for linter
                    if field_errors or errors:
                        raise ValidationError(errors, field_errors)
                try:
                    res = cls(**values)
                except (ValidationError, AssertionError):
                    raise
                except TypeError as err:
                    if str(err).startswith("__init__() got"):
                        raise Unsupported(cls)
                    else:
                        raise ValidationError([str(err)])
                except Exception as err:
                    raise ValidationError([str(err)])
                return validate(res, validators2, **init) if validators else res

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
        items_deserializers = [(key, self.method(tp)) for key, tp in types.items()]

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(dict, data)
                items: Dict[str, Any] = {}
                item_errors: Dict[ErrorKey, ValidationError] = {}
                for key, deserialize_item in items_deserializers:
                    if key in data:
                        try:
                            items[key] = deserialize_item(ctx, data[key])
                        except ValidationError as err:
                            if key not in defaults or not ctx.default_fallback:
                                item_errors[key] = err
                    elif key not in defaults:
                        item_errors[key] = ValidationError(["missing property"])

                if not ctx.additional_properties:
                    for key in sorted(data.keys() - defaults.keys() - items.keys()):
                        item_errors[key] = ValidationError(["unexpected property"])
                errors = () if constraints is None else constraints.errors(data)
                if item_errors or errors:
                    raise ValidationError(errors, item_errors)
                return cls(**items)

            return method

        return factory

    def new_type(
        self, cls: AnyType, super_type: AnyType
    ) -> DeserializationMethodFactory:
        return self.visit(super_type).merge(get_constraints(cls), get_validators(cls))

    def primitive(self, cls: Type) -> DeserializationMethodFactory:
        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            if constraints is None:
                method = lambda ctx, data: ctx.coercer(cls, data)  # noqa E731
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
        items_deserializers = {key: self.method(type_) for key, type_ in keys.items()}

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
                            item_errors[key] = ValidationError(["missing property"])
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
            methods = [fact.merge(constraints, validators).method for fact in factories]

            def method(ctx: DeserializationContext, data: Any) -> Any:
                # Optional optimization
                if data is None and optional:
                    return None
                error: Optional[ValidationError] = None
                for method in methods:
                    try:
                        return method(ctx, data)
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
        self, cls: Type, conversion: Deserialization
    ) -> DeserializationMethodFactory:
        factories = []
        for source, (converter, conversions) in conversion.items():
            with self._replace_conversions(conversions):
                factories.append((self.visit(source), converter))

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            methods = [
                (fact.merge(constraints, validators).method, converter)
                for fact, converter in factories
            ]

            def method(ctx: DeserializationContext, data: Any) -> Any:
                error: Optional[ValidationError] = None
                for method, converter in methods:
                    try:
                        value = method(ctx, data)
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
def get_method_without_conversions(cls: AnyType) -> DeserializationMethod:
    return DeserializationMethodVisitor(None).method(cls)


@cache
def get_method_with_conversions(
    wrapper: ConversionsWrapper, cls: AnyType
) -> DeserializationMethod:
    return DeserializationMethodVisitor(wrapper.conversions).method(cls)


@overload
def deserialize(
    cls: Type[T],
    data: Any,
    *,
    conversions: Conversions = None,
    additional_properties: bool = None,
    coercion: Coercion = None,
    default_fallback: bool = None,
) -> T:
    ...


@overload
def deserialize(
    cls: AnyType,
    data: Any,
    *,
    conversions: Conversions = None,
    additional_properties: bool = None,
    coercion: Coercion = None,
    default_fallback: bool = None,
) -> Any:
    ...


def deserialize(
    cls: AnyType,
    data: Any,
    *,
    conversions: Conversions = None,
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
    ctx = DeserializationContext(additional_properties, coercion, default_fallback)
    if conversions is None:
        method = get_method_without_conversions(cls)
    else:
        method = get_method_with_conversions(ConversionsWrapper(conversions), cls)
    return method(ctx, data)
