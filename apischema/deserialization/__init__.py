from collections import defaultdict
from dataclasses import dataclass, replace
from enum import Enum
from functools import lru_cache
from typing import (
    AbstractSet,
    Any,
    Callable,
    Collection,
    Dict,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    overload,
)

from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.visitor import (
    Deserialization,
    DeserializationVisitor,
    sub_conversion,
)
from apischema.dependencies import get_dependent_required
from apischema.deserialization.coercion import Coerce, Coercer
from apischema.deserialization.flattened import get_deserialization_flattened_aliases
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.types import bad_type
from apischema.metadata.implem import ValidatorsMetadata
from apischema.metadata.keys import SCHEMA_METADATA, VALIDATORS_METADATA
from apischema.objects import ObjectField
from apischema.objects.fields import FieldKind
from apischema.objects.visitor import DeserializationObjectVisitor
from apischema.recursion import RecursiveConversionsVisitor
from apischema.schemas import Schema, get_schema
from apischema.schemas.constraints import Check, Constraints, merge_constraints
from apischema.types import AnyType, NoneType
from apischema.typing import get_args, get_origin
from apischema.utils import (
    Lazy,
    PREFIX,
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

MISSING_PROPERTY = "missing property"
UNEXPECTED_PROPERTY = "unexpected property"

NOT_NONE = object()

INIT_VARS_ATTR = f"{PREFIX}_init_vars"

T = TypeVar("T")


DeserializationMethod = Callable[[Any], T]
Factory = Callable[[Optional[Constraints], Sequence[Validator]], DeserializationMethod]


@dataclass(frozen=True)
class DeserializationMethodFactory:
    factory: Factory
    cls: Optional[type] = None
    constraints: Optional[Constraints] = None
    validators: Tuple[Validator, ...] = ()

    def merge(
        self, constraints: Optional[Constraints], validators: Sequence[Validator] = ()
    ) -> "DeserializationMethodFactory":
        if constraints is None and not validators:
            return self
        return replace(
            self,
            constraints=merge_constraints(self.constraints, constraints),
            validators=(*validators, *self.validators),
        )

    @property  # type: ignore
    @lru_cache()
    def method(self) -> DeserializationMethod:
        return self.factory(self.constraints, self.validators)  # type: ignore


def get_constraints(schema: Optional[Schema]) -> Optional[Constraints]:
    return schema.constraints if schema is not None else None


def get_constraint_checks(
    constraints: Optional[Constraints], cls: type
) -> Collection[Tuple[Check, Any, str]]:
    return () if constraints is None else constraints.checks_by_type[cls]


class DeserializationMethodVisitor(
    RecursiveConversionsVisitor[Deserialization, DeserializationMethodFactory],
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
        self.additional_properties = additional_properties
        self.aliaser = aliaser
        self.coercer = coercer
        self.fall_back_on_default = fall_back_on_default

    def _recursive_result(
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

    def visit_not_recursive(self, tp: AnyType) -> DeserializationMethodFactory:
        return deserialization_method_factory(
            tp,
            self.additional_properties,
            self.aliaser,
            self.coercer,
            self._conversion,
            self.default_conversion,
            self.fall_back_on_default,
        )

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

    def _factory(
        self, factory: Factory, cls: Optional[type] = None, validation: bool = True
    ) -> DeserializationMethodFactory:
        def wrapper(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            method: DeserializationMethod
            if validation and validators:
                wrapped, aliaser = factory(constraints, ()), self.aliaser

                def method(data: Any) -> Any:
                    result = wrapped(data)
                    validate(result, validators, aliaser=aliaser)
                    return result

            else:
                method = factory(constraints, validators)
            if self.coercer is not None and cls is not None:
                coercer = self.coercer

                def wrapper(data: Any) -> Any:
                    assert cls is not None
                    return method(coercer(cls, data))

                return wrapper

            else:
                return method

        return DeserializationMethodFactory(wrapper, cls)

    def any(self) -> DeserializationMethodFactory:
        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            checks = None if constraints is None else constraints.checks_by_type

            def method(data: Any) -> Any:
                if checks is not None:
                    if data.__class__ in checks:
                        errors = [
                            err
                            for check, attr, err in checks[data.__class__]
                            if check(data, attr)
                        ]
                        if errors:
                            raise ValidationError(errors)
                return data

            return method

        return self._factory(factory)

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> DeserializationMethodFactory:
        value_factory = self.visit(value_type)

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            deserialize_value = value_factory.method
            checks = get_constraint_checks(constraints, list)
            constructor: Optional[Callable[[list], Collection]] = None
            if issubclass(cls, AbstractSet):
                constructor = set
            elif issubclass(cls, tuple):
                constructor = tuple

            def method(data: Any) -> Any:
                if not isinstance(data, list):
                    raise bad_type(data, list)
                elt_errors: Dict[ErrorKey, ValidationError] = {}
                values: list = [None] * len(data)
                index = 0  # don't use `enumerate` for performance
                for elt in data:
                    try:
                        values[index] = deserialize_value(elt)
                    except ValidationError as err:
                        elt_errors[index] = err
                    index += 1
                if checks:
                    errors = [err for check, attr, err in checks if check(data, attr)]
                    if errors or elt_errors:
                        raise ValidationError(errors, elt_errors)
                elif elt_errors:
                    raise ValidationError([], elt_errors)
                return constructor(values) if constructor else values

            return method

        return self._factory(factory, list)

    def enum(self, cls: Type[Enum]) -> DeserializationMethodFactory:
        return self.literal(list(cls))

    def literal(self, values: Sequence[Any]) -> DeserializationMethodFactory:
        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            value_map = dict(zip(literal_values(values), values))
            types = list(set(map(type, value_map))) if self.coercer else []
            error = f"not one of {list(value_map)}"
            coercer = self.coercer

            def method(data: Any) -> Any:
                try:
                    return value_map[data]
                except KeyError:
                    if coercer:
                        for cls in types:
                            try:
                                return value_map[coercer(cls, data)]
                            except IndexError:
                                pass
                    raise ValidationError([error])
                # Unions with Literal can have not hashable data
                except TypeError:
                    raise bad_type(data, *types)

            return method

        return self._factory(factory)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> DeserializationMethodFactory:
        key_factory, value_factory = self.visit(key_type), self.visit(value_type)

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            deserialize_key = key_factory.method
            deserialize_value = value_factory.method
            checks = get_constraint_checks(constraints, dict)

            def method(data: Any) -> Any:
                if not isinstance(data, dict):
                    raise bad_type(data, dict)
                item_errors: Dict[ErrorKey, ValidationError] = {}
                items = {}
                for key, value in data.items():
                    assert isinstance(key, str)
                    try:
                        items[deserialize_key(key)] = deserialize_value(value)
                    except ValidationError as err:
                        item_errors[key] = err
                if checks:
                    errors = [err for check, attr, err in checks if check(data, attr)]
                    if errors or item_errors:
                        raise ValidationError(errors, item_errors)
                elif item_errors:
                    raise ValidationError([], item_errors)
                return items

            return method

        return self._factory(factory, dict)

    def object(
        self, tp: Type, fields: Sequence[ObjectField]
    ) -> DeserializationMethodFactory:
        field_factories = [
            self.visit_with_conv(f.type, f.deserialization).merge(
                get_constraints(f.schema), f.validators
            )
            for f in fields
        ]

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            cls = get_origin_or_type(tp)
            alias_by_name = {field.name: self.aliaser(field.alias) for field in fields}
            requiring: Dict[str, Set[str]] = defaultdict(set)
            for f, reqs in get_dependent_required(cls).items():
                for req in reqs:
                    requiring[req].add(alias_by_name[f])
            normal_fields, flattened_fields, pattern_fields = [], [], []
            additional_field = None
            for field, field_factory in zip(fields, field_factories):
                deserialize_field: DeserializationMethod = field_factory.method
                fall_back_on_default = (
                    field.fall_back_on_default or self.fall_back_on_default
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
                            fall_back_on_default,
                        )
                    )
                elif field.pattern_properties is not None:
                    field_pattern = field.pattern_properties
                    if field_pattern is ...:
                        field_pattern = infer_pattern(
                            field.type, self.default_conversion
                        )
                    assert isinstance(field_pattern, Pattern)
                    pattern_fields.append(
                        (
                            field.name,
                            field_pattern,
                            deserialize_field,
                            fall_back_on_default,
                        )
                    )
                elif field.additional_properties:
                    additional_field = (
                        field.name,
                        deserialize_field,
                        fall_back_on_default,
                    )
                else:
                    normal_fields.append(
                        (
                            field.name,
                            self.aliaser(field.alias),
                            deserialize_field,
                            field.required,
                            requiring[field.name],
                            fall_back_on_default,
                        )
                    )
            has_aggregate_field = (
                flattened_fields or pattern_fields or (additional_field is not None)
            )
            post_init_modified = {field.name for field in fields if field.post_init}
            checks = get_constraint_checks(constraints, dict)
            aliaser = self.aliaser
            additional_properties = self.additional_properties
            all_aliases = set(alias_by_name.values())
            init_defaults = [
                (f.name, f.default_factory)
                for f in fields
                if f.kind == FieldKind.WRITE_ONLY
            ]

            def method(data: Any) -> Any:
                if not isinstance(data, dict):
                    raise bad_type(data, dict)
                values: Dict[str, Any] = {}
                fields_count = 0
                errors = (
                    [err for check, attr, err in checks if check(data, attr)]
                    if checks
                    else []
                )
                field_errors: Dict[ErrorKey, ValidationError] = {}
                for (
                    name,
                    alias,
                    deserialize_field,
                    required,
                    required_by,
                    fall_back_on_default,
                ) in normal_fields:
                    if required:
                        try:
                            value = data[alias]
                        except KeyError:
                            field_errors[alias] = ValidationError([MISSING_PROPERTY])
                        else:
                            fields_count += 1
                            try:
                                values[name] = deserialize_field(value)
                            except ValidationError as err:
                                field_errors[alias] = err
                    elif alias in data:
                        fields_count += 1
                        try:
                            values[name] = deserialize_field(data[alias])
                        except ValidationError as err:
                            if not fall_back_on_default:
                                field_errors[alias] = err
                    elif required_by and not required_by.isdisjoint(data):
                        requiring = sorted(required_by & data.keys())
                        msg = f"missing property (required by {requiring})"
                        field_errors[alias] = ValidationError([msg])
                if has_aggregate_field:
                    remain = data.keys() - all_aliases
                    for (
                        name,
                        flattened_alias,
                        deserialize_field,
                        fall_back_on_default,
                    ) in flattened_fields:
                        flattened = {
                            alias: data[alias]
                            for alias in flattened_alias
                            if alias in data
                        }
                        remain.difference_update(flattened)
                        try:
                            values[name] = deserialize_field(flattened)
                        except ValidationError as err:
                            if not fall_back_on_default:
                                errors.extend(err.messages)
                                field_errors.update(err.children)
                    for (
                        name,
                        pattern,
                        deserialize_field,
                        fall_back_on_default,
                    ) in pattern_fields:
                        matched = {
                            key: data[key] for key in remain if pattern.match(key)
                        }
                        remain.difference_update(matched)
                        try:
                            values[name] = deserialize_field(matched)
                        except ValidationError as err:
                            if not fall_back_on_default:
                                errors.extend(err.messages)
                                field_errors.update(err.children)
                    if additional_field:
                        name, deserialize_field, fall_back_on_default = additional_field
                        additional = {key: data[key] for key in remain}
                        try:
                            values[name] = deserialize_field(additional)
                        except ValidationError as err:
                            if not fall_back_on_default:
                                errors.extend(err.messages)
                                field_errors.update(err.children)
                    elif remain and not additional_properties:
                        for key in remain:
                            field_errors[key] = ValidationError([UNEXPECTED_PROPERTY])
                elif not additional_properties and len(data) != fields_count:
                    for key in data.keys() - all_aliases:
                        field_errors[key] = ValidationError([UNEXPECTED_PROPERTY])
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
                        v
                        for v in validators
                        if not v.dependencies.isdisjoint(values.keys())
                    ]
                    if field_errors or errors:
                        error = ValidationError(errors, field_errors)
                        invalid_fields = field_errors.keys() | post_init_modified
                        try:
                            validate(
                                ValidatorMock(cls, values),
                                [
                                    v
                                    for v in validators2
                                    if v.dependencies.isdisjoint(invalid_fields)
                                ],
                                init,
                                aliaser=aliaser,
                            )
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
                if validators:
                    validate(res, validators2, init, aliaser=aliaser)
                return res

            return method

        return self._factory(factory, dict, validation=False)

    def primitive(self, cls: Type) -> DeserializationMethodFactory:
        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            checks = get_constraint_checks(constraints, cls)
            if cls is NoneType:

                def method(data: Any) -> Any:
                    if data is not None:
                        raise bad_type(data, cls)
                    return data

            elif cls is not float and not checks:

                def method(data: Any) -> Any:
                    if not isinstance(data, cls):
                        raise bad_type(data, cls)
                    return data

            elif cls is not float and len(checks) == 1:
                ((check, attr, err),) = checks

                def method(data: Any) -> Any:
                    if not isinstance(data, cls):
                        raise bad_type(data, cls)
                    elif check(data, attr):
                        raise ValidationError([err])
                    return data

            else:
                is_float = cls is float

                def method(data: Any) -> Any:
                    if not isinstance(data, cls):
                        if is_float and isinstance(data, int):
                            data = float(data)
                        else:
                            raise bad_type(data, cls)
                    if checks:
                        errors = [
                            err for check, attr, err in checks if check(data, attr)
                        ]
                        if errors:
                            raise ValidationError(errors)
                    return data

            return method

        return self._factory(factory, cls)

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

        return replace(primitive_factory, factory=factory)

    def tuple(self, types: Sequence[AnyType]) -> DeserializationMethodFactory:
        elt_factories = [self.visit(tp) for tp in types]

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            expected_len = len(types)
            (_, _, min_err), (_, _, max_err) = Constraints(
                min_items=len(types), max_items=len(types)
            ).checks_by_type[list]
            elt_methods = list(enumerate(fact.method for fact in elt_factories))
            checks = get_constraint_checks(constraints, list)

            def method(data: Any) -> Any:
                if not isinstance(data, list):
                    raise bad_type(data, list)
                if len(data) != expected_len:
                    raise ValidationError([min_err, max_err])
                elt_errors: Dict[ErrorKey, ValidationError] = {}
                elts: List[Any] = [None] * expected_len
                for i, deserialize_elt in elt_methods:
                    try:
                        elts[i] = deserialize_elt(data[i])
                    except ValidationError as err:
                        elt_errors[i] = err
                if checks:
                    errors = [err for check, attr, err in checks if check(data, attr)]
                    if errors or elt_errors:
                        raise ValidationError(errors, elt_errors)
                elif elt_errors:
                    raise ValidationError([], elt_errors)
                return tuple(elts)

            return method

        return self._factory(factory, list)

    def union(self, alternatives: Sequence[AnyType]) -> DeserializationMethodFactory:
        alt_factories = self._union_results(alternatives)
        if len(alt_factories) == 1:
            return alt_factories[0]

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            alt_methods = [fact.merge(constraints).method for fact in alt_factories]
            # method_by_cls cannot replace alt_methods, because there could be several
            # methods for one class
            method_by_cls = dict(zip((f.cls for f in alt_factories), alt_methods))
            if NoneType in alternatives and len(alt_methods) == 2:
                deserialize_alt = next(
                    meth
                    for fact, meth in zip(alt_factories, alt_methods)
                    if fact.cls is not NoneType
                )
                coercer = self.coercer

                def method(data: Any) -> Any:
                    if data is None:
                        return None
                    try:
                        return deserialize_alt(data)
                    except ValidationError as err:
                        if coercer and coercer(NoneType, data) is None:
                            return None
                        else:
                            raise merge_errors(err, bad_type(data, NoneType))

            elif None not in method_by_cls and len(method_by_cls) == len(alt_factories):
                classes = tuple(cls for cls in method_by_cls if cls is not None)

                def method(data: Any) -> Any:
                    try:
                        return method_by_cls[data.__class__](data)
                    except KeyError:
                        raise bad_type(data, *classes) from None
                    except ValidationError as err:
                        other_classes = (
                            cls for cls in classes if cls is not data.__class__
                        )
                        raise merge_errors(err, bad_type(data, *other_classes))

            else:

                def method(data: Any) -> Any:
                    error = None
                    for deserialize_alt in alt_methods:
                        try:
                            return deserialize_alt(data)
                        except ValidationError as err:
                            error = merge_errors(error, err)
                    assert error is not None
                    raise error

            return method

        return self._factory(factory)

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Deserialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> DeserializationMethodFactory:
        assert conversion
        conv_factories = [
            self.visit_with_conv(conv.source, sub_conversion(conv, next_conversion))
            for conv in conversion
        ]

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            conv_methods = [
                ((fact if dynamic else fact.merge(constraints)).method, conv.converter)
                for conv, fact in zip(conversion, conv_factories)
            ]
            method: DeserializationMethod
            if len(conv_methods) == 1:
                deserialize_alt, converter = conv_methods[0]

                def method(data: Any) -> Any:
                    try:
                        return converter(deserialize_alt(data))
                    except (ValidationError, AssertionError):
                        raise
                    except Exception as err:
                        raise ValidationError([str(err)])

            else:

                def method(data: Any) -> Any:
                    error: Optional[ValidationError] = None
                    for deserialize_alt, converter in conv_methods:
                        try:
                            value = deserialize_alt(data)
                        except ValidationError as err:
                            error = merge_errors(error, err)
                        else:
                            try:
                                return converter(value)
                            except (ValidationError, AssertionError):
                                raise
                            except Exception as err:
                                raise ValidationError([str(err)])
                    assert error is not None
                    raise error

            return method

        return self._factory(factory, validation=not dynamic)

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Deserialization],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> DeserializationMethodFactory:
        factory = super().visit_conversion(tp, conversion, dynamic, next_conversion)
        if not dynamic:
            factory = factory.merge(get_constraints(get_schema(tp)), get_validators(tp))
            if get_args(tp):
                factory = factory.merge(
                    get_constraints(get_schema(get_origin(tp))),
                    get_validators(get_origin(tp)),
                )
        return factory


@cache
def deserialization_method_factory(
    tp: AnyType,
    additional_properties: bool,
    aliaser: Aliaser,
    coercer: Optional[Coercer],
    conversion: Optional[AnyConversion],
    default_conversion: DefaultConversion,
    fall_back_on_default: bool,
) -> DeserializationMethodFactory:
    return DeserializationMethodVisitor(
        additional_properties,
        aliaser,
        coercer,
        default_conversion,
        fall_back_on_default,
    ).visit_with_conv(tp, conversion)


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

    coercer: Optional[Coercer] = None
    if callable(coerce):
        coercer = coerce
    elif opt_or(coerce, settings.deserialization.coerce):
        coercer = settings.deserialization.coercer
    return (
        deserialization_method_factory(
            type,
            opt_or(additional_properties, settings.additional_properties),
            opt_or(aliaser, settings.aliaser),
            coercer,
            conversion,
            opt_or(default_conversion, settings.deserialization.default_conversion),
            opt_or(fall_back_on_default, settings.deserialization.fall_back_on_default),
        )
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
