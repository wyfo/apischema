from abc import ABC, abstractmethod
from dataclasses import Field, dataclass, field, is_dataclass, replace
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
from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.coercion import Coercion, get_coercer
from apischema.conversions.metadata import get_field_conversions
from apischema.conversions.utils import Conversions, ConversionsWrapper, identity
from apischema.conversions.visitor import Deserialization, DeserializationVisitor
from apischema.dataclass_utils import (
    check_merged_class,
    dataclass_types_and_fields,
    get_alias,
    get_default,
    get_required_by,
    has_default,
    is_required,
)
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
from apischema.utils import map_values
from apischema.validation.errors import (
    ErrorKey,
    FieldPath,
    ValidationError,
    apply_aliaser,
    merge_errors,
)
from apischema.validation.mock import ValidatorMock
from apischema.validation.validator import (
    Validator,
    ValidatorsMetadata,
    get_validators,
    validate,
)
from apischema.visitor import Unsupported

DICT_TYPE = get_origin(Dict[Any, Any])
LIST_TYPE = get_origin(List[Any])

T = TypeVar("T")


# TODO maybe ctx parameters to deserializers
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


@dataclass(frozen=True)  # type: ignore
class DeserializationField(ABC):
    base_field: Field
    method: DeserializationMethod
    name: str = field(init=False)
    required: bool = field(init=False)
    default: bool = field(init=False)
    default_fallback: bool = field(init=False)

    def __post_init__(self):
        super().__setattr__("name", self.base_field.name)
        super().__setattr__("required", is_required(self.base_field))
        super().__setattr__("default", has_default(self.base_field))
        super().__setattr__(
            "default_fallback",
            DEFAULT_FALLBACK_METADATA in self.base_field.metadata,
        )

    @abstractmethod
    def error_handler(
        self,
        error: ValidationError,
        errors: List[str],
        field_errors: Dict[ErrorKey, ValidationError],
    ):
        ...

    def deserialize(
        self,
        ctx: DeserializationContext,
        data: Any,
        values: Dict[str, Any],
        errors: List[str],
        field_errors: Dict[ErrorKey, ValidationError],
    ):
        try:
            values[self.name] = self.method(ctx, data)  # type: ignore
        except ValidationError as err:
            if self.default and (self.default_fallback or ctx.default_fallback):
                pass
            else:
                self.error_handler(err, errors, field_errors)


class NormalField(DeserializationField):
    def error_handler(
        self,
        error: ValidationError,
        errors: List[str],
        field_errors: Dict[ErrorKey, ValidationError],
    ):
        field_errors[FieldPath(self.base_field)] = error


class AggregateField(DeserializationField):
    def error_handler(
        self,
        error: ValidationError,
        errors: List[str],
        field_errors: Dict[ErrorKey, ValidationError],
    ):
        errors.extend(error.messages)
        field_errors.update(error.children)


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


def get_init_merged_alias(merged_cls: Type) -> Iterable[str]:
    from apischema.metadata.keys import MERGED_METADATA

    merged_cls = check_merged_class(merged_cls)
    types, fields, init_vars = dataclass_types_and_fields(merged_cls)  # type: ignore
    for field in chain(fields, init_vars):  # noqa: F402
        if not field.init:
            continue
        if MERGED_METADATA in field.metadata:
            yield from get_init_merged_alias(types[field.name])
        else:
            yield get_alias(field)


class DeserializationMethodVisitor(
    DeserializationVisitor[DeserializationMethodFactory]
):
    def __init__(self, aliaser: Aliaser):
        super().__init__()
        self._rec_sentinel: Dict[Any, RecDeserializerMethodFactory] = {}
        self.aliaser = aliaser

    def _visit(self, cls: AnyType) -> DeserializationMethodFactory:
        key = self._resolve_type_vars(cls), id(self._conversions)
        if key in self._rec_sentinel:
            return cast(DeserializationMethodFactory, self._rec_sentinel[key])
        else:
            self._rec_sentinel[key] = RecDeserializerMethodFactory()
            factory = super()._visit(cls)
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
        assert is_dataclass(cls)
        normal_fields: List[Tuple[str, DeserializationField]] = []
        merged_fields: List[Tuple[AbstractSet[str], DeserializationField]] = []
        pattern_fields: List[Tuple[Pattern, DeserializationField]] = []
        additional_field: Optional[DeserializationField] = None
        post_init_modified = {
            field.name
            for field in chain(fields, init_vars)
            if POST_INIT_METADATA in field.metadata
        }
        defaults: Dict[str, Callable[[], Any]] = {}
        required_by = {
            req.name: {self.aliaser(get_alias(dep)) for dep in deps}
            for req, deps in get_required_by(cls)[0].items()
        }
        for field in chain(fields, init_vars):  # noqa: F402
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
                field_factory = self.visit_with_conversions(
                    field_type, conversions.deserialization
                )
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
            field_class = AggregateField if is_aggregate_field(field) else NormalField
            field2 = field_class(field, field_factory.method)
            if MERGED_METADATA in metadata:
                merged_fields.append(
                    (set(map(self.aliaser, get_init_merged_alias(field_type))), field2)
                )
            elif PROPERTIES_METADATA in metadata:
                pattern = metadata[PROPERTIES_METADATA]
                if pattern is None:
                    additional_field = field2
                elif pattern is ...:
                    pattern_fields.append((infer_pattern(field_type), field2))
                else:
                    pattern_fields.append((pattern, field2))
            else:
                normal_fields.append((self.aliaser(get_alias(field)), field2))

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
                            ctx, data[alias], values, errors, field_errors
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
                        invalid_fields = field_errors.keys() | post_init_modified
                        validators2 = [
                            v
                            for v in validators2
                            if not v.dependencies & invalid_fields
                        ]
                        try:
                            validate(ValidatorMock(cls, values), validators2, **init)
                        except ValidationError as err:
                            error = merge_errors(error, err)
                        raise apply_aliaser(error, self.aliaser)
                elif field_errors or errors:
                    raise apply_aliaser(
                        ValidationError(errors, field_errors), self.aliaser
                    )
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
                        item_errors[alias] = ValidationError(["missing property"])

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
        items_deserializers = map_values(self.method, keys)

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
        self, cls: AnyType, conversion: Deserialization
    ) -> DeserializationMethodFactory:
        assert conversion
        factories = [
            (self.visit_with_conversions(source, conversions), converter)
            for source, (converter, conversions) in conversion.items()
        ]

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            alt_deserializers = [
                (fact.merge(constraints, validators).method, converter)
                for fact, converter in factories
            ]
            if len(alt_deserializers) == 1:
                ((deserialize_alt, converter),) = alt_deserializers
                if converter is identity:
                    method = deserialize_alt
                else:

                    def method(ctx: DeserializationContext, data: Any) -> Any:
                        try:
                            return converter(deserialize_alt(ctx, data))
                        except (ValidationError, AssertionError):
                            raise
                        except Exception as err:
                            raise ValidationError([str(err)])

            else:

                def method(ctx: DeserializationContext, data: Any) -> Any:
                    error: Optional[ValidationError] = None
                    for deserialize_alt, converter in alt_deserializers:
                        try:
                            value = deserialize_alt(ctx, data)
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
    cls: AnyType,
    wrapper: Optional[ConversionsWrapper],
    aliaser: Aliaser,
) -> DeserializationMethod:
    conversions = wrapper.conversions if wrapper is not None else None
    factory = DeserializationMethodVisitor(aliaser).visit_with_conversions(
        cls, conversions
    )
    return factory.method


@overload
def deserialize(
    cls: Type[T],
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
    cls: AnyType,
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
    cls: AnyType,
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
    wrapper = ConversionsWrapper(conversions) if conversions is not None else None
    return get_method(cls, wrapper, aliaser)(ctx, data)
