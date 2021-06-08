from collections import defaultdict
from dataclasses import dataclass, replace
from enum import Enum
from functools import wraps
from typing import (
    AbstractSet,
    Any,
    Callable,
    Dict,
    Hashable,
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
    overload,
)

from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.utils import identity
from apischema.conversions.visitor import (
    CachedConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    sub_conversion,
)
from apischema.dependencies import get_dependent_required
from apischema.deserialization.coercion import Coerce, Coercer, get_coercer
from apischema.deserialization.flattened import get_deserialization_flattened_aliases
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.types import bad_type
from apischema.metadata.implem import ValidatorsMetadata
from apischema.metadata.keys import SCHEMA_METADATA, VALIDATORS_METADATA
from apischema.objects import ObjectField
from apischema.objects.fields import FieldKind
from apischema.objects.visitor import DeserializationObjectVisitor
from apischema.schemas import Schema, get_schema
from apischema.schemas.constraints import Constraints, merge_constraints
from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    NoneType,
    OrderedDict,
    UndefinedType,
)
from apischema.typing import get_args, get_origin
from apischema.utils import (
    Lazy,
    PREFIX,
    context_setter,
    deprecate_kwargs,
    get_origin_or_type,
    literal_values,
    opt_or,
)
from apischema.validation import get_validators
from apischema.validation.errors import ErrorKey, ValidationError, merge_errors
from apischema.validation.mock import ValidatorMock
from apischema.validation.validators import Validator, validate
from apischema.visitor import Unsupported

DICT_TYPE = get_origin(Dict[Any, Any])
LIST_TYPE = get_origin(List[Any])

MISSING_PROPERTY = ValidationError(["missing property"])
UNEXPECTED_PROPERTY = ValidationError(["unexpected property"])

NOT_NONE = object()

INIT_VARS_ATTR = f"{PREFIX}_init_vars"

T = TypeVar("T")


DeserializationMethod = Callable[[Any], T]


@dataclass(frozen=True)
class DeserializationMethodFactory:
    factory: Callable[
        [Optional[Constraints], Sequence[Validator]], DeserializationMethod
    ]
    data_type: Optional[Type] = None
    coercer: Optional[Coercer] = None
    constraints: Optional[Constraints] = None
    validators: Sequence[Validator] = ()

    def merge(
        self, constraints: Optional[Constraints], validators: Sequence[Validator]
    ) -> "DeserializationMethodFactory":
        if constraints is None and not validators:
            return self
        return replace(
            self,
            constraints=merge_constraints(self.constraints, constraints),
            validators=(*validators, *self.validators),
        )

    @property
    def method(self) -> DeserializationMethod:
        method = self.factory(self.constraints, self.validators)  # type: ignore

        if self.data_type is not None and self.coercer is not None:
            wrapped_for_coercion, coercer, cls = method, self.coercer, self.data_type

            @wraps(method)
            def method(data: Any) -> Any:
                return wrapped_for_coercion(coercer(cls, data))

        return method


FallBakOnDefault = bool
Required = Union[bool, AbstractSet[str]]


def get_constraints(schema: Optional[Schema]) -> Optional[Constraints]:
    return schema.constraints if schema is not None else None


def with_validators(
    method: DeserializationMethod, validators: Sequence[Validator]
) -> DeserializationMethod:
    if not validators:
        return method

    @wraps(method)
    def wrapper(data: Any) -> Any:
        return validate(method(data), validators)

    return wrapper


def get_constraint_errors(
    constraints: Optional[Constraints], cls: type
) -> Optional[Callable[[Any], Sequence[str]]]:
    return None if constraints is None else constraints.errors_by_type.get(cls)


class DeserializationMethodVisitor(
    CachedConversionsVisitor[Deserialization, DeserializationMethodFactory],
    DeserializationVisitor[DeserializationMethodFactory],
    DeserializationObjectVisitor[DeserializationMethodFactory],
):
    def __init__(
        self,
        additional_properties: bool,
        aliaser: Aliaser,
        coercer: Optional[Coercer],
        default_conversion: DefaultConversion,
        fall_back_on_default: bool,
    ):
        super().__init__(default_conversion)
        self._additional_properties = additional_properties
        self.aliaser = aliaser
        self._coercer = coercer
        self._fall_back_on_default = fall_back_on_default

    def _cache_key(self) -> Hashable:
        return self._coercer

    def _cache_result(
        self, lazy: Lazy[DeserializationMethodFactory]
    ) -> DeserializationMethodFactory:
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            rec_method = None

            def method(data: Any) -> Any:
                nonlocal rec_method
                if rec_method is None:
                    rec_method = lazy().merge(constraints, validators).method
                return rec_method(data)

            return method

        return DeserializationMethodFactory(factory)

    def annotated(
        self, tp: AnyType, annotations: Sequence[Any]
    ) -> DeserializationMethodFactory:
        factory = super().annotated(tp, annotations)
        for annotation in reversed(annotations):
            if isinstance(annotation, Mapping):
                factory = factory.merge(
                    get_constraints(annotation.get(SCHEMA_METADATA)),
                    annotation.get(
                        VALIDATORS_METADATA, ValidatorsMetadata(())
                    ).validators,
                )
        return factory

    def any(self) -> DeserializationMethodFactory:
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            def method(data: Any) -> Any:
                if constraints is not None:
                    cls = type(data)
                    if cls in constraints.errors_by_type:
                        errors = constraints.errors_by_type[cls](data)
                        if errors:
                            raise ValidationError(errors)
                return data

            return with_validators(method, validators)

        return DeserializationMethodFactory(factory)

    def collection(
        self, cls: Type[Iterable], value_type: AnyType
    ) -> DeserializationMethodFactory:
        value_factory = self.visit(value_type)

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            deserialize_value = value_factory.method
            constraint_errors = get_constraint_errors(constraints, list)

            def method(data: Any) -> Any:
                if not isinstance(data, list):
                    raise bad_type(data, list)
                elts = []
                elt_errors: Dict[ErrorKey, ValidationError] = {}
                for i, elt in enumerate(data):
                    try:
                        elts.append(deserialize_value(elt))
                    except ValidationError as err:
                        elt_errors[i] = err
                errors = constraint_errors(data) if constraint_errors else ()
                if elt_errors or errors:
                    raise ValidationError(errors, elt_errors)
                return elts if cls is LIST_TYPE else COLLECTION_TYPES[cls](elts)

            return with_validators(method, validators)

        return DeserializationMethodFactory(factory, list)

    def enum(self, cls: Type[Enum]) -> DeserializationMethodFactory:
        literal_factory = self.literal([elt.value for elt in cls])

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            deserialize_literal = literal_factory.merge(constraints, validators).method

            def method(data: Any) -> Any:
                return cls(deserialize_literal(data))

            return method

        return DeserializationMethodFactory(factory)

    def literal(self, values: Sequence[Any]) -> DeserializationMethodFactory:
        primitive_values = literal_values(values)
        any_factory = self.any()

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            deserialize_any = any_factory.merge(constraints, validators).method

            def method(data: Any) -> Any:
                try:
                    result = values[primitive_values.index(data)]
                except ValueError:
                    raise ValidationError([f"not one of {primitive_values}"])
                deserialize_any(data)  # for validation
                return result

            return method

        return DeserializationMethodFactory(factory)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> DeserializationMethodFactory:
        key_factory, value_factory = self.visit(key_type), self.visit(value_type)

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            deserialize_key = key_factory.method
            deserialize_value = value_factory.method
            constraint_errors = get_constraint_errors(constraints, dict)

            def method(data: Any) -> Any:
                if not isinstance(data, dict):
                    raise bad_type(data, dict)
                items = {}
                item_errors: Dict[ErrorKey, ValidationError] = {}
                for key, value in data.items():
                    assert isinstance(key, str)
                    try:
                        items[deserialize_key(key)] = deserialize_value(value)
                    except ValidationError as err:
                        item_errors[key] = err
                errors = constraint_errors(data) if constraint_errors else ()
                if item_errors or errors:
                    raise ValidationError(errors, item_errors)
                return items if cls is DICT_TYPE else MAPPING_TYPES[cls](items)

            return with_validators(method, validators)

        return DeserializationMethodFactory(factory, dict)

    def object(
        self, tp: Type, fields: Sequence[ObjectField]
    ) -> DeserializationMethodFactory:
        field_factories = [
            self.visit_with_conv(f.type, f.deserialization).merge(
                get_constraints(f.schema), f.validators
            )
            for f in fields
        ]
        additional_properties = self._additional_properties
        fall_back_on_default = self._fall_back_on_default

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            cls = get_origin_or_type(tp)
            normal_fields: List[
                Tuple[str, str, DeserializationMethod, Required, FallBakOnDefault]
            ] = []
            flattened_fields: List[
                Tuple[str, AbstractSet[str], DeserializationMethod, FallBakOnDefault]
            ] = []
            pattern_fields: List[
                Tuple[str, Pattern, DeserializationMethod, FallBakOnDefault]
            ] = []
            additional_field: Optional[
                Tuple[str, DeserializationMethod, FallBakOnDefault]
            ] = None
            post_init_modified = {field.name for field in fields if field.post_init}
            alias_by_name = {field.name: self.aliaser(field.alias) for field in fields}
            requiring: Dict[str, Set[str]] = defaultdict(set)
            for f, reqs in get_dependent_required(cls).items():
                for req in reqs:
                    requiring[req].add(alias_by_name[f])
            init_defaults = [
                (f.name, f.default_factory)
                for f in fields
                if f.kind == FieldKind.WRITE_ONLY
            ]
            for field, field_factory in zip(fields, field_factories):
                deserialize_field = field_factory.method
                field_fall_back_on_default = (
                    field.fall_back_on_default or fall_back_on_default
                )
                if field.flattened:
                    flattened_aliases = get_deserialization_flattened_aliases(
                        cls, field, self.default_conversion
                    )
                    flattened_fields.append(
                        (
                            field.name,
                            set(map(self.aliaser, flattened_aliases)),
                            deserialize_field,
                            field_fall_back_on_default,
                        )
                    )
                elif field.pattern_properties is ...:
                    pattern_fields.append(
                        (
                            field.name,
                            infer_pattern(field.type, self.default_conversion),
                            deserialize_field,
                            field_fall_back_on_default,
                        )
                    )
                elif field.pattern_properties is not None:
                    assert isinstance(field.pattern_properties, Pattern)
                    pattern_fields.append(
                        (
                            field.name,
                            field.pattern_properties,
                            deserialize_field,
                            field_fall_back_on_default,
                        )
                    )
                elif field.additional_properties:
                    additional_field = (
                        field.name,
                        deserialize_field,
                        field_fall_back_on_default,
                    )
                else:
                    normal_fields.append(
                        (
                            field.name,
                            self.aliaser(field.alias),
                            deserialize_field,
                            field.required or requiring[field.name],
                            field_fall_back_on_default,
                        )
                    )
            has_aggregate_field = (
                flattened_fields or pattern_fields or (additional_field is not None)
            )
            constraint_errors = get_constraint_errors(constraints, dict)

            def method(data: Any) -> Any:
                if not isinstance(data, dict):
                    raise bad_type(data, dict)
                values: Dict[str, Any] = {}
                aliases: List[str] = []
                errors = list(constraint_errors(data)) if constraint_errors else []
                field_errors: Dict[ErrorKey, ValidationError] = OrderedDict()
                for (
                    name,
                    alias,
                    field_method,
                    required,
                    fall_back_on_default,
                ) in normal_fields:
                    if alias in data:
                        aliases.append(alias)
                        try:
                            values[name] = field_method(data[alias])
                        except ValidationError as err:
                            if not fall_back_on_default:
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
                if has_aggregate_field:
                    for (
                        name,
                        flattened_alias,
                        field_method,
                        fall_back_on_default,
                    ) in flattened_fields:

                        flattened = {
                            alias: data[alias]
                            for alias in flattened_alias
                            if alias in data
                        }
                        aliases.extend(flattened)
                        try:
                            values[name] = field_method(flattened)
                        except ValidationError as err:
                            if not fall_back_on_default:
                                errors.extend(err.messages)
                                field_errors.update(err.children)
                    if len(data) != len(aliases):
                        remain = data.keys() - set(aliases)
                    else:
                        remain = set()
                    for (
                        name,
                        pattern,
                        field_method,
                        fall_back_on_default,
                    ) in pattern_fields:
                        matched = {
                            key: data[key] for key in remain if pattern.match(key)
                        }
                        remain -= matched.keys()
                        try:
                            values[name] = field_method(matched)
                        except ValidationError as err:
                            if not fall_back_on_default:
                                errors.extend(err.messages)
                                field_errors.update(err.children)
                    if additional_field is not None:
                        name, field_method, fall_back_on_default = additional_field
                        additional = {key: data[key] for key in remain}
                        try:
                            values[name] = field_method(additional)
                        except ValidationError as err:
                            if not fall_back_on_default:
                                errors.extend(err.messages)
                                field_errors.update(err.children)
                    elif remain and not additional_properties:
                        for key in remain:
                            field_errors[key] = UNEXPECTED_PROPERTY
                elif len(data) != len(aliases) and not additional_properties:
                    for key in data.keys() - set(aliases):
                        field_errors[key] = UNEXPECTED_PROPERTY

                validators2: Sequence[Validator]
                if validators:
                    init: Dict[str, Any] = {}
                    for name, default_factory in init_defaults:
                        if name in values:
                            init[name] = values[name]
                        elif name not in field_errors:
                            assert default_factory is not None
                            init[name] = default_factory()
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
                    validators2, init = (), ...  # type: ignore # only for linter
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
                if validators2:
                    validate(res, validators2, **init)
                return res

            return method

        return DeserializationMethodFactory(factory, dict)

    def primitive(self, cls: Type) -> DeserializationMethodFactory:
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            if constraints is not None and cls in constraints.errors_by_type:
                constraint_errors = constraints.errors_by_type[cls]

                def method(data: Any) -> Any:
                    if not isinstance(data, cls):
                        if cls == float and isinstance(data, int):
                            data = float(data)
                        else:
                            raise bad_type(data, cls)
                    if data is not None:
                        errors = constraint_errors(data)
                        if errors:
                            raise ValidationError(errors)
                    return data

            else:

                def method(data: Any) -> Any:
                    if isinstance(data, cls):
                        return data
                    elif cls == float and isinstance(data, int):
                        return float(data)
                    else:
                        raise bad_type(data, cls)

            return with_validators(method, validators)

        return DeserializationMethodFactory(factory, cls)

    def subprimitive(self, cls: Type, superclass: Type) -> DeserializationMethodFactory:
        primitive_factory = self.primitive(superclass)

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            deserialize_primitive = primitive_factory.merge(
                constraints, validators
            ).method

            def method(data: Any) -> Any:
                return superclass(deserialize_primitive(data))

            return method

        return DeserializationMethodFactory(factory)

    def tuple(self, types: Sequence[AnyType]) -> DeserializationMethodFactory:
        nb_elts, elt_factories = len(types), [self.visit(tp) for tp in types]

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            elt_deserializers = [elt_factory.method for elt_factory in elt_factories]
            tuple_constraints = merge_constraints(
                constraints, Constraints(min_items=nb_elts, max_items=nb_elts)
            )
            constraint_errors = get_constraint_errors(tuple_constraints, list)

            def method(data: Any) -> Any:
                if not isinstance(data, list):
                    raise bad_type(data, list)
                elts: List[Any] = []
                elt_errors: Dict[ErrorKey, ValidationError] = {}
                for i, (deserialize_elt, elt) in enumerate(
                    zip(elt_deserializers, data)
                ):
                    try:
                        elts.append(deserialize_elt(elt))
                    except ValidationError as err:
                        elt_errors[i] = err
                errors = constraint_errors(data) if constraint_errors else ()
                if elt_errors or errors:
                    raise ValidationError(errors, elt_errors)
                return tuple(elts)

            return with_validators(method, validators)

        return DeserializationMethodFactory(factory, list)

    def union(self, alternatives: Sequence[AnyType]) -> DeserializationMethodFactory:
        none_check = None if NoneType in alternatives else NOT_NONE
        alt_factories = [
            self.visit(alt) for alt in alternatives if alt not in (None, UndefinedType)
        ]

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            alt_deserializers = [
                factory.merge(constraints, validators).method
                for factory in alt_factories
            ]

            def method(data: Any) -> Any:
                # Optional optimization
                if data is none_check:
                    return None
                error: Optional[ValidationError] = None
                for deserialize_alt in alt_deserializers:
                    try:
                        return deserialize_alt(data)
                    except ValidationError as err:
                        error = merge_errors(error, err)
                if none_check is None:
                    error = merge_errors(error, bad_type(data, NoneType))
                if error is None:  # empty union
                    return data
                else:
                    raise error

            return method

        return DeserializationMethodFactory(factory)

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Deserialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> DeserializationMethodFactory:
        assert conversion
        conv_factories = []
        for conv in conversion:
            with context_setter(self) as setter:
                if conv.additional_properties is not None:
                    setter._additional_properties = conv.additional_properties
                if conv.fall_back_on_default is not None:
                    setter._fall_back_on_default = conv.fall_back_on_default
                if conv.coerce is not None:
                    setter._coercer = get_coercer(conv.coerce)
                sub_conv = sub_conversion(conv, next_conversion)
                conv_factories.append(self.visit_with_conv(conv.source, sub_conv))

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            conv_factories2 = conv_factories
            if not dynamic:
                conv_factories2 = [
                    fact.merge(constraints, validators) for fact in conv_factories
                ]
            conv_deserializers = [
                (fact.method, conv.converter)
                for conv, fact in zip(conversion, conv_factories2)
            ]
            method: DeserializationMethod
            if len(conv_deserializers) > 1:

                def method(data: Any) -> Any:
                    error: Optional[ValidationError] = None
                    for deserialize_conv, converter in conv_deserializers:
                        try:
                            value = deserialize_conv(data)
                            break
                        except ValidationError as err:
                            error = merge_errors(error, err)
                    else:
                        assert error is not None
                        raise error
                    try:
                        return converter(value)  # type: ignore
                    except (ValidationError, AssertionError):
                        raise
                    except Exception as err:
                        raise ValidationError([str(err)])

            elif conv_deserializers[0][1] is identity:
                method, _ = conv_deserializers[0]
            else:
                conv_deserializer, converter = conv_deserializers[0]

                def method(data: Any) -> Any:
                    try:
                        return converter(conv_deserializer(data))  # type: ignore
                    except (ValidationError, AssertionError):
                        raise
                    except Exception as err:
                        raise ValidationError([str(err)])

            return method

        return DeserializationMethodFactory(factory)

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Deserialization],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> DeserializationMethodFactory:
        factory = super().visit_conversion(tp, conversion, dynamic, next_conversion)
        if factory.coercer is None and self._coercer is not None:
            factory = replace(factory, coercer=self._coercer)
        if not dynamic:
            factory = factory.merge(get_constraints(get_schema(tp)), get_validators(tp))
            if get_args(tp):
                factory = factory.merge(
                    get_constraints(get_schema(get_origin(tp))),
                    get_validators(get_origin(tp)),
                )
        return factory


@overload
def deserialization_method(
    type: Type[T],
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    schema: Schema = None,
) -> DeserializationMethod[T]:
    ...


@overload
def deserialization_method(
    type: AnyType,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    schema: Schema = None,
) -> DeserializationMethod:
    ...


@cache
def deserialization_method(
    type: AnyType,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    schema: Schema = None,
) -> DeserializationMethod:
    from apischema import settings

    return (
        DeserializationMethodVisitor(
            opt_or(
                additional_properties, settings.deserialization.additional_properties
            ),
            opt_or(aliaser, settings.aliaser),
            get_coercer(opt_or(coerce, settings.deserialization.coerce)),
            opt_or(default_conversion, settings.deserialization.default_conversion),
            opt_or(fall_back_on_default, settings.deserialization.fall_back_on_default),
        )
        .visit_with_conv(type, conversion)
        .merge(get_constraints(schema), ())
        .method
    )


@overload
def deserialize(
    type: Type[T],
    data: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    schema: Schema = None,
) -> T:
    ...


@overload
def deserialize(
    type: AnyType,
    data: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    schema: Schema = None,
) -> Any:
    ...


@deprecate_kwargs(
    {
        "coercion": "coerce",
        "conversions": "conversion",
        "default_fallback": "fall_back_on_default",
    }
)
def deserialize(
    type: AnyType,
    data: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    schema: Schema = None,
) -> Any:
    return deserialization_method(
        type,
        additional_properties=additional_properties,
        aliaser=aliaser,
        coerce=coerce,
        conversion=conversion,
        default_conversion=default_conversion,
        fall_back_on_default=fall_back_on_default,
        schema=schema,
    )(data)
