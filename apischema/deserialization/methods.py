from dataclasses import dataclass, field
from typing import (
    AbstractSet,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Union,
)

from apischema.aliases import Aliaser
from apischema.conversions.utils import Converter
from apischema.deserialization.coercion import Coercer
from apischema.json_schema.types import bad_type
from apischema.types import AnyType, NoneType
from apischema.utils import Lazy
from apischema.validation.errors import (
    ErrorKey,
    ErrorMsg,
    ValidationError,
    merge_errors,
)
from apischema.validation.mock import ValidatorMock
from apischema.validation.validators import Validator, validate


@dataclass
class Constraint:
    error: Union[str, Callable[[Any], str]]

    def validate(self, data: Any) -> bool:
        raise NotImplementedError


@dataclass
class MinimumConstraint(Constraint):
    minimum: int

    def validate(self, data: Any) -> bool:
        return data >= self.minimum


@dataclass
class MaximumConstraint(Constraint):
    maximum: int

    def validate(self, data: Any) -> bool:
        return data <= self.maximum


@dataclass
class ExclusiveMinimumConstraint(Constraint):
    exc_min: int

    def validate(self, data: Any) -> bool:
        return data > self.exc_min


@dataclass
class ExclusiveMaximumConstraint(Constraint):
    exc_max: int

    def validate(self, data: Any) -> bool:
        return data < self.exc_max


@dataclass
class MultipleOfConstraint(Constraint):
    mult_of: int

    def validate(self, data: Any) -> bool:
        return not (data % self.mult_of)


@dataclass
class MinLengthConstraint(Constraint):
    min_len: int

    def validate(self, data: Any) -> bool:
        return len(data) >= self.min_len


@dataclass
class MaxLengthConstraint(Constraint):
    max_len: int

    def validate(self, data: Any) -> bool:
        return len(data) <= self.max_len


@dataclass
class PatternConstraint(Constraint):
    pattern: Pattern

    def validate(self, data: Any) -> bool:
        return self.pattern.match(data) is not None


@dataclass
class MinItemsConstraint(Constraint):
    min_items: int

    def validate(self, data: Any) -> bool:
        return len(data) >= self.min_items


@dataclass
class MaxItemsConstraint(Constraint):
    max_items: int

    def validate(self, data: Any) -> bool:
        return len(data) <= self.max_items


def to_hashable(data: Any) -> Any:
    if isinstance(data, list):
        return tuple(map(to_hashable, data))
    elif isinstance(data, dict):
        sorted_keys = sorted(data)
        return tuple(sorted_keys + [to_hashable(data[k]) for k in sorted_keys])
    else:
        return data


@dataclass
class UniqueItemsConstraint(Constraint):
    unique: bool

    def __post_init__(self):
        assert self.unique

    def validate(self, data: Any) -> bool:
        return len(set(map(to_hashable, data))) == len(data)


@dataclass
class MinPropertiesConstraint(Constraint):
    min_properties: int

    def validate(self, data: Any) -> bool:
        return len(data) >= self.min_properties


@dataclass
class MaxPropertiesConstraint(Constraint):
    max_properties: int

    def validate(self, data: Any) -> bool:
        return len(data) <= self.max_properties


def format_error(err: Union[str, Callable[[Any], str]], data: Any) -> str:
    return err if isinstance(err, str) else err(data)


ErrorDict = Dict[ErrorKey, ValidationError]


def validate_constraints(
    data: Any, constraints: Tuple[Constraint, ...], children_errors: Optional[ErrorDict]
) -> Any:
    for i in range(len(constraints)):
        constraint: Constraint = constraints[i]
        if not constraint.validate(data):
            errors: List[str] = [format_error(constraint.error, data)]
            for j in range(i + 1, len(constraints)):
                constraint = constraints[j]
                if not constraint.validate(data):
                    errors.append(format_error(constraint.error, data))
            raise ValidationError(errors, children_errors or {})
    if children_errors:
        raise ValidationError([], children_errors)
    return data


def set_child_error(
    errors: Optional[ErrorDict], key: ErrorKey, error: ValidationError
) -> ErrorDict:
    if errors is None:
        return {key: error}
    else:
        errors[key] = error
        return errors


class DeserializationMethod:
    def deserialize(self, data: Any) -> Any:
        raise NotImplementedError


@dataclass
class RecMethod(DeserializationMethod):
    lazy: Lazy[DeserializationMethod]
    method: Optional[DeserializationMethod] = field(init=False)

    def __post_init__(self):
        self.method = None

    def deserialize(self, data: Any) -> Any:
        if self.method is None:
            self.method = self.lazy()
        return self.method.deserialize(data)


@dataclass
class ValidatorMethod(DeserializationMethod):
    method: DeserializationMethod
    validators: Sequence[Validator]
    aliaser: Aliaser

    def deserialize(self, data: Any) -> Any:
        return validate(
            self.method.deserialize(data), self.validators, aliaser=self.aliaser
        )


@dataclass
class CoercerMethod(DeserializationMethod):
    coercer: Coercer
    cls: type
    method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        return self.method.deserialize(self.coercer(self.cls, data))


@dataclass
class TypeCheckMethod(DeserializationMethod):
    expected: AnyType  # `type` would require exact match (i.e. no EnumMeta)
    fallback: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        if isinstance(data, self.expected):
            return data
        return self.fallback.deserialize(data)


@dataclass
class AnyMethod(DeserializationMethod):
    constraints: Dict[type, Tuple[Constraint, ...]]

    def deserialize(self, data: Any) -> Any:
        if type(data) in self.constraints:
            validate_constraints(data, self.constraints[type(data)], None)
        return data


@dataclass
class ListCheckOnlyMethod(DeserializationMethod):
    constraints: Tuple[Constraint, ...]
    value_method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, list):
            raise bad_type(data, list)
        elt_errors: Optional[ErrorDict] = None
        for i, elt in enumerate(data):
            try:
                self.value_method.deserialize(elt)
            except ValidationError as err:
                elt_errors = set_child_error(elt_errors, i, err)
        validate_constraints(data, self.constraints, elt_errors)
        return data


@dataclass
class ListMethod(DeserializationMethod):
    constraints: Tuple[Constraint, ...]
    value_method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, list):
            raise bad_type(data, list)
        elt_errors: Optional[ErrorDict] = None
        values: list = [None] * len(data)
        for i, elt in enumerate(data):
            try:
                values[i] = self.value_method.deserialize(elt)
            except ValidationError as err:
                elt_errors = set_child_error(elt_errors, i, err)
        validate_constraints(data, self.constraints, elt_errors)
        return values


@dataclass
class SetMethod(DeserializationMethod):
    constraints: Tuple[Constraint, ...]
    value_method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, list):
            raise bad_type(data, list)
        elt_errors: ErrorDict = {}
        values: set = set()
        for i, elt in enumerate(data):
            try:
                values.add(self.value_method.deserialize(elt))
            except ValidationError as err:
                elt_errors = set_child_error(elt_errors, i, err)
        validate_constraints(data, self.constraints, elt_errors)
        return values


@dataclass
class FrozenSetMethod(DeserializationMethod):
    method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        return frozenset(self.method.deserialize(data))


@dataclass
class VariadicTupleMethod(DeserializationMethod):
    method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        return tuple(self.method.deserialize(data))


@dataclass
class LiteralMethod(DeserializationMethod):
    value_map: dict
    error: Union[str, Callable[[Any], str]]
    coercer: Optional[Coercer]
    types: Tuple[type, ...]

    def deserialize(self, data: Any) -> Any:
        try:
            return self.value_map[data]
        except KeyError:
            if self.coercer is not None:
                for cls in self.types:
                    try:
                        return self.value_map[self.coercer(cls, data)]
                    except IndexError:
                        pass
            raise ValidationError(format_error(self.error, data))
        except TypeError:
            raise bad_type(data, *self.types)


@dataclass
class MappingCheckOnly(DeserializationMethod):
    constraints: Tuple[Constraint, ...]
    key_method: DeserializationMethod
    value_method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        item_errors: Optional[ErrorDict] = None
        for key, value in data.items():
            try:
                self.key_method.deserialize(key)
                self.value_method.deserialize(value)
            except ValidationError as err:
                item_errors = set_child_error(item_errors, key, err)
        validate_constraints(data, self.constraints, item_errors)
        return data


@dataclass
class MappingMethod(DeserializationMethod):
    constraints: Tuple[Constraint, ...]
    key_method: DeserializationMethod
    value_method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        item_errors: Optional[ErrorDict] = None
        items: dict = {}
        for key, value in data.items():
            try:
                items[self.key_method.deserialize(key)] = self.value_method.deserialize(
                    value
                )
            except ValidationError as err:
                item_errors = set_child_error(item_errors, key, err)
        validate_constraints(data, self.constraints, item_errors)
        return items


@dataclass
class Field:
    name: str
    alias: str
    method: DeserializationMethod
    required: bool
    required_by: Optional[AbstractSet[str]]
    fall_back_on_default: bool


@dataclass
class FlattenedField:
    name: str
    aliases: Tuple[str, ...]
    method: DeserializationMethod
    fall_back_on_default: bool


@dataclass
class PatternField:
    name: str
    pattern: Pattern
    method: DeserializationMethod
    fall_back_on_default: bool


@dataclass
class AdditionalField:
    name: str
    method: DeserializationMethod
    fall_back_on_default: bool


@dataclass
class Constructor:
    cls: Any  # cython doesn't handle type subclasses properly

    def construct(self, fields: Dict[str, Any]) -> Any:
        raise NotImplementedError


class NoConstructor(Constructor):
    def construct(self, fields: Dict[str, Any]) -> Any:
        return fields


def PyObject_Call(obj, args, kwargs):
    return obj(*args, **kwargs)


class RawConstructor(Constructor):
    def construct(self, fields: Dict[str, Any]) -> Any:
        return PyObject_Call(self.cls, (), fields)


class RawConstructorCopy(Constructor):
    def construct(self, fields: Dict[str, Any]) -> Any:
        return self.cls(**fields)


@dataclass
class DefaultField:
    name: str
    default_value: Any  # https://github.com/cython/cython/issues/4383


@dataclass
class FactoryField:
    name: str
    factory: Callable


@dataclass
class FieldsConstructor(Constructor):
    nb_fields: int
    default_fields: Tuple[DefaultField, ...]
    factory_fields: Tuple[FactoryField, ...]

    def construct(self, fields: Any) -> Any:  # fields can be a dict subclass
        obj = object.__new__(self.cls)
        obj_dict: dict = obj.__dict__
        obj_dict.update(fields)
        if len(fields) != self.nb_fields:
            for default_field in self.default_fields:
                if default_field.name not in obj_dict:
                    obj_dict[default_field.name] = default_field.default_value
            for factory_field in self.factory_fields:
                if factory_field.name not in obj_dict:
                    obj_dict[factory_field.name] = factory_field.factory()
        return obj


@dataclass
class SimpleObjectMethod(DeserializationMethod):
    constructor: Constructor
    fields: Tuple[Field, ...]
    all_aliases: AbstractSet[str]
    typed_dict: bool
    missing: str
    unexpected: str

    def deserialize(self, data: Any) -> Any:
        discriminator: Optional[str] = None
        if not isinstance(data, dict):
            if isinstance(data, Discriminated):
                discriminator = data.discriminator
                data = data.data
                if not isinstance(data, dict):
                    raise bad_type(data, dict)
            else:
                raise bad_type(data, dict)
        fields_count: int = 0
        field_errors: Optional[dict] = None
        for field in self.fields:
            if field.alias in data:
                fields_count += 1
                try:
                    field.method.deserialize(data[field.alias])
                except ValidationError as err:
                    if field.required or not field.fall_back_on_default:
                        field_errors = set_child_error(field_errors, field.alias, err)
            elif field.required:
                field_errors = set_child_error(
                    field_errors, field.alias, ValidationError(self.missing)
                )
        has_discriminator = False
        if len(data) != fields_count and not self.typed_dict:
            for key in data.keys() - self.all_aliases:
                if key == discriminator:
                    has_discriminator = True
                else:
                    field_errors = set_child_error(
                        field_errors, key, ValidationError(self.unexpected)
                    )
        if field_errors:
            raise ValidationError([], field_errors)
        if has_discriminator:
            data = data.copy()
            del data[discriminator]
        return self.constructor.construct(data)


def extend_errors(
    errors: Optional[List[ErrorMsg]], messages: Sequence[ErrorMsg]
) -> List[ErrorMsg]:
    if errors is None:
        return list(messages)
    else:
        errors.extend(messages)
        return errors


def update_children_errors(
    errors: Optional[Dict[ErrorKey, ValidationError]],
    children: Mapping[ErrorKey, ValidationError],
) -> Dict[ErrorKey, ValidationError]:
    if errors is None:
        return dict(children)
    else:
        errors.update(children)
        return errors


@dataclass
class ObjectMethod(DeserializationMethod):
    constructor: Constructor
    constraints: Tuple[Constraint, ...]
    fields: Tuple[Field, ...]
    flattened_fields: Tuple[FlattenedField, ...]
    pattern_fields: Tuple[PatternField, ...]
    additional_field: Optional[AdditionalField]
    all_aliases: AbstractSet[str]
    additional_properties: bool
    typed_dict: bool
    validators: Tuple[Validator, ...]
    init_defaults: Tuple[Tuple[str, Optional[Callable[[], Any]]], ...]
    post_init_modified: AbstractSet[str]
    aliaser: Aliaser
    missing: str
    unexpected: str
    aggregate_fields: bool = field(init=False)

    def __post_init__(self):
        self.aggregate_fields = bool(
            self.flattened_fields
            or self.pattern_fields
            or self.additional_field is not None
        )

    def deserialize(self, data: Any) -> Any:
        discriminator: Optional[str] = None
        if not isinstance(data, dict):
            if isinstance(data, Discriminated):
                discriminator = data.discriminator
                data = data.data
                if not isinstance(data, dict):
                    raise bad_type(data, dict)
            else:
                raise bad_type(data, dict)
        values: dict = {}
        fields_count: int = 0
        errors: Optional[list] = None
        try:
            validate_constraints(data, self.constraints, None)
        except ValidationError as err:
            errors = list(err.messages)
        field_errors: Optional[dict] = None
        for field in self.fields:
            if field.alias in data:
                fields_count += 1
                try:
                    values[field.name] = field.method.deserialize(data[field.alias])
                except ValidationError as err:
                    if field.required or not field.fall_back_on_default:
                        field_errors = set_child_error(field_errors, field.alias, err)
            elif field.required:
                field_errors = set_child_error(
                    field_errors, field.alias, ValidationError(self.missing)
                )
            elif field.required_by is not None and not field.required_by.isdisjoint(
                data
            ):
                requiring = sorted(field.required_by & data.keys())
                error = ValidationError([self.missing + f" (required by {requiring})"])
                field_errors = set_child_error(field_errors, field.alias, error)
        if self.aggregate_fields:
            remain = data.keys() - self.all_aliases
            for flattened_field in self.flattened_fields:
                flattened: dict = {
                    alias: data[alias]
                    for alias in flattened_field.aliases
                    if alias in data
                }
                remain.difference_update(flattened)
                try:
                    values[flattened_field.name] = flattened_field.method.deserialize(
                        flattened
                    )
                except ValidationError as err:
                    if not flattened_field.fall_back_on_default:
                        errors = extend_errors(errors, err.messages)
                        field_errors = update_children_errors(
                            field_errors, err.children
                        )
            for pattern_field in self.pattern_fields:
                matched: dict = {
                    key: data[key] for key in remain if pattern_field.pattern.match(key)
                }
                remain.difference_update(matched)
                try:
                    values[pattern_field.name] = pattern_field.method.deserialize(
                        matched
                    )
                except ValidationError as err:
                    if not pattern_field.fall_back_on_default:
                        errors = extend_errors(errors, err.messages)
                        field_errors = update_children_errors(
                            field_errors, err.children
                        )
            if self.additional_field is not None:
                additional: dict = {key: data[key] for key in remain}
                try:
                    values[self.additional_field.name] = (
                        self.additional_field.method.deserialize(additional)
                    )
                except ValidationError as err:
                    if not self.additional_field.fall_back_on_default:
                        errors = extend_errors(errors, err.messages)
                        field_errors = update_children_errors(
                            field_errors, err.children
                        )
            elif remain:
                if not self.additional_properties:
                    for key in remain:
                        if key != discriminator:
                            field_errors = set_child_error(
                                field_errors, key, ValidationError(self.unexpected)
                            )
                elif self.typed_dict:
                    for key in remain:
                        values[key] = data[key]
        elif len(data) != fields_count:
            if not self.additional_properties:
                for key in data.keys() - self.all_aliases:
                    if key != discriminator:
                        field_errors = set_child_error(
                            field_errors, key, ValidationError(self.unexpected)
                        )
            elif self.typed_dict:
                for key in data.keys() - self.all_aliases:
                    values[key] = data[key]
        if self.validators:
            init = None
            if self.init_defaults:
                init = {}
                for name, default_factory in self.init_defaults:
                    if name in values:
                        init[name] = values[name]
                    elif not field_errors or name not in field_errors:
                        assert default_factory is not None
                        init[name] = default_factory()
            aliases = values.keys()
            # Don't keep validators when all dependencies are default
            validators = [
                v for v in self.validators if not v.dependencies.isdisjoint(aliases)
            ]
            if field_errors or errors:
                error = ValidationError(errors or [], field_errors or {})
                invalid_fields = self.post_init_modified
                if field_errors:
                    invalid_fields = invalid_fields | field_errors.keys()
                try:
                    validate(
                        ValidatorMock(self.constructor.cls, values),
                        [
                            v
                            for v in validators
                            if v.dependencies.isdisjoint(invalid_fields)
                        ],
                        init,
                        aliaser=self.aliaser,
                    )
                except ValidationError as err:
                    error = merge_errors(error, err)
                raise error
            obj = self.constructor.construct(values)
            return validate(obj, validators, init, aliaser=self.aliaser)
        elif field_errors or errors:
            raise ValidationError(errors or [], field_errors or {})
        return self.constructor.construct(values)


class NoneMethod(DeserializationMethod):
    def deserialize(self, data: Any) -> Any:
        if data is not None:
            raise bad_type(data, NoneType)
        return data


class IntMethod(DeserializationMethod):
    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, int) or isinstance(data, bool):
            raise bad_type(data, int)
        return data


class FloatMethod(DeserializationMethod):
    def deserialize(self, data: Any) -> Any:
        if isinstance(data, float):
            return data
        elif isinstance(data, int):
            return float(data)
        else:
            raise bad_type(data, float)


class StrMethod(DeserializationMethod):
    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, str):
            raise bad_type(data, str)
        return data


class BoolMethod(DeserializationMethod):
    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, bool):
            raise bad_type(data, bool)
        return data


@dataclass
class ConstrainedIntMethod(IntMethod):
    constraints: Tuple[Constraint, ...]

    def deserialize(self, data: Any) -> Any:
        return validate_constraints(super().deserialize(data), self.constraints, None)


@dataclass
class ConstrainedFloatMethod(FloatMethod):
    constraints: Tuple[Constraint, ...]

    def deserialize(self, data: Any) -> Any:
        return validate_constraints(super().deserialize(data), self.constraints, None)


@dataclass
class ConstrainedStrMethod(StrMethod):
    constraints: Tuple[Constraint, ...]

    def deserialize(self, data: Any) -> Any:
        return validate_constraints(super().deserialize(data), self.constraints, None)


@dataclass
class SubprimitiveMethod(DeserializationMethod):
    cls: type
    method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        return self.cls(self.method.deserialize(data))


@dataclass
class TupleMethod(DeserializationMethod):
    constraints: Tuple[Constraint, ...]
    min_len_error: Union[str, Callable[[Any], str]]
    max_len_error: Union[str, Callable[[Any], str]]
    elt_methods: Tuple[DeserializationMethod, ...]

    def deserialize(self, data: Any) -> Any:
        if not isinstance(data, list):
            raise bad_type(data, list)
        data_len = len(data)
        if data_len != len(self.elt_methods):
            if data_len < len(self.elt_methods):
                raise ValidationError(format_error(self.min_len_error, data))
            elif data_len > len(self.elt_methods):
                raise ValidationError(format_error(self.max_len_error, data))
            else:
                raise NotImplementedError
        elt_errors: Optional[ErrorDict] = None
        elts: list = [None] * len(self.elt_methods)
        for i, elt_method in enumerate(self.elt_methods):
            try:
                elts[i] = elt_method.deserialize(data[i])
            except ValidationError as err:
                set_child_error(elt_errors, i, err)
        validate_constraints(data, self.constraints, elt_errors)
        return tuple(elts)


@dataclass
class OptionalMethod(DeserializationMethod):
    value_method: DeserializationMethod
    coercer: Optional[Coercer]

    def deserialize(self, data: Any) -> Any:
        if data is None:
            return None
        try:
            return self.value_method.deserialize(data)
        except ValidationError as err:
            if self.coercer is not None and self.coercer(NoneType, data) is None:
                return None
            else:
                raise merge_errors(err, bad_type(data, NoneType))


@dataclass
class UnionByTypeMethod(DeserializationMethod):
    method_by_cls: Dict[type, DeserializationMethod]

    def deserialize(self, data: Any) -> Any:
        try:
            method: DeserializationMethod = self.method_by_cls[type(data)]
            return method.deserialize(data)
        except KeyError:
            raise bad_type(data, *self.method_by_cls) from None
        except ValidationError as err:
            other_classes = (cls for cls in self.method_by_cls if cls is not type(data))
            raise merge_errors(err, bad_type(data, *other_classes))


@dataclass
class UnionMethod(DeserializationMethod):
    alt_methods: Tuple[DeserializationMethod, ...]

    def deserialize(self, data: Any) -> Any:
        error = None
        for i, alt_method in enumerate(self.alt_methods):
            try:
                return alt_method.deserialize(data)
            except ValidationError as err:
                error = merge_errors(error, err)
        assert error is not None
        raise error


@dataclass
class ConversionMethod(DeserializationMethod):
    converter: Converter
    method: DeserializationMethod

    def deserialize(self, data: Any) -> Any:
        return self.converter(self.method.deserialize(data))


@dataclass
class ConversionWithValueErrorMethod(ConversionMethod):
    def deserialize(self, data: Any) -> Any:
        value = self.method.deserialize(data)
        try:
            return self.converter(value)
        except ValueError as err:
            raise ValidationError(str(err))


@dataclass
class ConversionAlternative:
    converter: Converter
    method: DeserializationMethod
    value_error: bool


@dataclass
class ConversionUnionMethod(DeserializationMethod):
    alternatives: Tuple[ConversionAlternative, ...]

    def deserialize(self, data: Any) -> Any:
        error = None
        for alternative in self.alternatives:
            try:
                value = alternative.method.deserialize(data)
            except ValidationError as err:
                error = merge_errors(error, err)
                continue
            try:
                return alternative.converter(value)
            except ValidationError as err:
                error = merge_errors(error, err)
            except ValueError as err:
                if not alternative.value_error:
                    raise
                error = merge_errors(error, ValidationError(str(err)))
        assert error is not None
        raise error


@dataclass
class Discriminated:
    discriminator: str
    data: Any


@dataclass
class DiscriminatorMethod(DeserializationMethod):
    alias: str
    mapping: Dict[str, DeserializationMethod]
    missing: str
    error: Union[str, Callable[[Any], str]]

    def deserialize(self, data: Any):
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        if self.alias not in data:
            raise ValidationError([], {self.alias: ValidationError(self.missing)})
        try:
            method: DeserializationMethod = self.mapping[data[self.alias]]
        except (TypeError, KeyError):
            raise ValidationError(
                [],
                {
                    self.alias: ValidationError(
                        format_error(self.error, data[self.alias])
                    )
                },
            )
        else:
            return method.deserialize(Discriminated(self.alias, data))
