from collections import defaultdict
from collections.abc import Collection as Collection_
from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import wraps
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
    Set,
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
from apischema.conversions.conversions import Conversions, HashableConversions
from apischema.conversions.utils import Converter, identity
from apischema.conversions.visitor import Deserialization, DeserializationVisitor
from apischema.dataclasses import replace
from apischema.dependencies import get_dependent_required
from apischema.deserialization.coercion import Coercion, get_coercer
from apischema.deserialization.merged import get_deserialization_merged_aliases
from apischema.json_schema.constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
    merge_constraints,
)
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.schemas import Schema, get_schema
from apischema.metadata.implem import ValidatorsMetadata
from apischema.metadata.keys import SCHEMA_METADATA, VALIDATORS_METADATA
from apischema.objects import AliasedStr, ObjectField
from apischema.objects.visitor import DeserializationObjectVisitor
from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    NoneType,
    OrderedDict,
    UndefinedType,
)
from apischema.typing import get_origin
from apischema.utils import get_origin_or_type, opt_or
from apischema.validation.errors import ErrorKey, ValidationError, merge_errors
from apischema.validation.mock import ValidatorMock
from apischema.validation.validators import Validator, get_validators, validate
from apischema.visitor import Unsupported, dataclass_types_and_fields

DICT_TYPE = get_origin(Dict[Any, Any])
LIST_TYPE = get_origin(List[Any])

MISSING_PROPERTY = ValidationError(["missing property"])
UNEXPECTED_PROPERTY = ValidationError(["unexpected property"])

T = TypeVar("T")


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


DefaultFallback = Optional[bool]
Required = Union[bool, AbstractSet[str]]


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
    DeserializationObjectVisitor[DeserializationMethodFactory],
    DeserializationVisitor[DeserializationMethodFactory],
):
    def __init__(self, aliaser: Aliaser):
        super().__init__()
        self._rec_sentinel: Dict[Any, RecDeserializerMethodFactory] = {}

        def _aliaser(s: str) -> str:
            return aliaser(s) if isinstance(s, AliasedStr) else s

        self.aliaser = _aliaser

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

    def new_type(
        self, tp: AnyType, super_type: AnyType
    ) -> DeserializationMethodFactory:
        return self.visit(super_type).merge(get_constraints(tp), get_validators(tp))

    def object(
        self, cls: Type, fields: Sequence[ObjectField]
    ) -> DeserializationMethodFactory:
        normal_fields: List[
            Tuple[str, str, DeserializationMethod, Required, DefaultFallback]
        ] = []
        merged_fields: List[
            Tuple[str, AbstractSet[str], DeserializationMethod, DefaultFallback]
        ] = []
        pattern_fields: List[
            Tuple[str, Pattern, DeserializationMethod, DefaultFallback]
        ] = []
        additional_field: Optional[
            Tuple[str, DeserializationMethod, DefaultFallback]
        ] = None
        post_init_modified = {field.name for field in fields if field.post_init}
        defaults: Dict[str, Callable[[], Any]] = {
            f.name: f.default_factory for f in fields if not f.required  # type: ignore
        }
        alias_by_name = {field.name: self.aliaser(field.alias) for field in fields}
        requiring: Dict[str, Set[str]] = defaultdict(set)
        for f, reqs in get_dependent_required(cls).items():
            for req in reqs:
                requiring[req].add(alias_by_name[f])
        if is_dataclass(cls):
            _, _, init_vars = dataclass_types_and_fields(cls)  # type: ignore
        else:
            init_vars = ()
        for field in fields:
            field_factory = self.visit_with_conversions(
                field.type, field.deserialization
            )
            field_method = field_factory.merge(
                field.constraints, field.validators
            ).method
            default_fallback = None if field.required else field.default_fallback
            if field.merged:
                merged_aliases = get_deserialization_merged_aliases(cls, field)
                merged_fields.append(
                    (
                        field.name,
                        set(map(self.aliaser, merged_aliases)),
                        field_method,
                        default_fallback,
                    )
                )
            elif field.pattern_properties is ...:
                pattern_fields.append(
                    (
                        field.name,
                        infer_pattern(field.type),
                        field_method,
                        default_fallback,
                    )
                )
            elif field.pattern_properties is not None:
                assert isinstance(field.pattern_properties, Pattern)
                pattern_fields.append(
                    (
                        field.name,
                        field.pattern_properties,
                        field_method,
                        default_fallback,
                    )
                )
            elif field.additional_properties:
                additional_field = (field.name, field_method, default_fallback)
            else:
                normal_fields.append(
                    (
                        field.name,
                        self.aliaser(field.alias),
                        field_method,
                        field.required or requiring[field.name],
                        default_fallback,
                    )
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
                for (
                    name,
                    alias,
                    field_method,
                    required,
                    default_fallback,
                ) in normal_fields:
                    if alias in data:
                        aliases.append(alias)
                        try:
                            values[name] = field_method(ctx, data[alias])
                        except ValidationError as err:
                            if default_fallback is None or not (
                                default_fallback or ctx.default_fallback
                            ):
                                field_errors[alias] = err
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
                for (
                    name,
                    merged_alias,
                    field_method,
                    default_fallback,
                ) in merged_fields:
                    merged = {
                        alias: data[alias] for alias in merged_alias if alias in data
                    }
                    aliases.extend(merged)
                    try:
                        values[name] = field_method(ctx, merged)
                    except ValidationError as err:
                        if default_fallback is None or not (
                            default_fallback or ctx.default_fallback
                        ):
                            errors.extend(err.messages)
                            field_errors.update(err.children)
                if len(data) != len(aliases):
                    remain = data.keys() - set(aliases)
                else:
                    remain = set()
                for name, pattern, field_method, default_fallback in pattern_fields:
                    matched = {key: data[key] for key in remain if pattern.match(key)}
                    remain -= matched.keys()
                    try:
                        values[name] = field_method(ctx, matched)
                    except ValidationError as err:
                        if default_fallback is None or not (
                            default_fallback or ctx.default_fallback
                        ):
                            errors.extend(err.messages)
                            field_errors.update(err.children)
                if additional_field is not None:
                    name, field_method, default_fallback = additional_field
                    additional = {key: data[key] for key in remain}
                    try:
                        values[name] = field_method(ctx, additional)
                    except ValidationError as err:
                        if default_fallback is None or not (
                            default_fallback or ctx.default_fallback
                        ):
                            errors.extend(err.messages)
                            field_errors.update(err.children)
                elif remain and not ctx.additional_properties:
                    for key in remain:
                        field_errors[key] = UNEXPECTED_PROPERTY
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
                        raise error
                elif field_errors or errors:
                    raise ValidationError(errors, field_errors)
                else:
                    validators2, init = ..., ...  # type: ignore # only for linter
                try:
                    res = cls(**values)
                except (AssertionError, ValidationError):
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

    def primitive(self, cls: Type) -> DeserializationMethodFactory:
        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            if constraints is None:

                def method(ctx: DeserializationContext, data: Any) -> Any:
                    return ctx.coercer(cls, data)

            else:

                def method(ctx: DeserializationContext, data: Any) -> Any:
                    data = ctx.coercer(cls, data)
                    assert constraints is not None
                    if data is not None:
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
        elts_deserializers = [self.method(cls) for cls in types]

        @DeserializationMethodFactory
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            @with_validators(validators)
            def method(ctx: DeserializationContext, data: Any) -> Any:
                data = ctx.coercer(list, data)
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

        return factory.merge(
            constraints=ArrayConstraints(min_items=len(types), max_items=len(types))
        )

    def union(self, alternatives: Sequence[AnyType]) -> DeserializationMethodFactory:
        factories = [
            self.visit(alt) for alt in alternatives if alt is not UndefinedType
        ]
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
                conv,
                self.visit_with_conversions(conv.source, conv.sub_conversions),
            )
            for conv in conversion
        ]

        @DeserializationMethodFactory.from_type(cls)
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            alt_deserializers = [
                (
                    fact.merge(constraints if not dynamic else None).method,
                    cast(Converter, conv.converter),
                    (conv.additional_properties, conv.coercion, conv.default_fallback),
                )
                for conv, fact in factories
            ]
            if len(alt_deserializers) == 1:
                deserialize_alt, converter, conv_ctx = alt_deserializers[0]
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

                if conv_ctx != (None, None, None):
                    wrapped = method

                    def method(ctx: DeserializationContext, data: Any) -> Any:
                        return wrapped(ctx.merge(*conv_ctx), data)

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

            return with_validators(validators)(method)

        return factory


@cache
def get_method(
    tp: AnyType, conversions: Optional[HashableConversions], aliaser: Aliaser
) -> DeserializationMethod:
    factory = DeserializationMethodVisitor(aliaser).visit_with_conversions(
        tp, conversions
    )
    return factory.method


constraints_type: Mapping[Type[Constraints], Type] = {
    NumberConstraints: float,
    StringConstraints: str,
    ArrayConstraints: list,
    ObjectConstraints: dict,
}


@overload
def deserialize(
    tp: Type[T],
    data: Any,
    *,
    conversions: Conversions = None,
    schema: Schema = None,
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
    schema: Schema = None,
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
    schema: Schema = None,
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
    if schema is not None and schema.constraints is not None:
        schema.constraints.validate(
            ctx.coercer(constraints_type[type(schema.constraints)], data)
        )
    if conversions is not None and isinstance(conversions, Collection_):
        conversions = tuple(conversions)
    return get_method(tp, conversions, aliaser)(ctx, data)
