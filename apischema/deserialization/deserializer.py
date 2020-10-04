from enum import Enum
from typing import (
    Any,
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
    overload,
)

from apischema import settings
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import (
    Deserialization,
    DeserializationVisitor,
)
from apischema.dataclasses import is_dataclass
from apischema.dataclasses.cache import (
    Field,
    get_deserialization_fields,
    get_post_init_fields,
)
from apischema.deserialization.coercion import Coercer, Coercion, get_coercer
from apischema.json_schema.constraints import (
    ArrayConstraints,
    Constraints,
    get_constraints,
)
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.schema import Schema
from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    DICT_TYPE,
    LIST_TYPE,
    MAPPING_TYPES,
    NoneType,
    OrderedDict,
    Skip,
    Skipped,
)
from apischema.utils import get_default
from apischema.validation.errors import (
    ErrorKey,
    ErrorMsg,
    ValidationError,
    merge_errors,
)
from apischema.validation.mock import ValidatorMock
from apischema.validation.validator import (
    Validator,
    ValidatorsMetadata,
    get_validators,
    validate,
)


def not_one_of(values: Iterable[Any]) -> ValidationError:
    allowed_values = [
        value if not isinstance(value, Enum) else value.value for value in values
    ]
    return ValidationError([f"not one of {allowed_values}"])


def validate_with_errors(
    data: Any,
    constraints: Optional[Constraints],
    errors: Mapping[ErrorKey, ValidationError],
):
    if constraints is not None:
        try:
            constraints.validate(data)
        except ValidationError as err:
            raise ValidationError(err.messages, errors)
    if errors:
        raise ValidationError(children=errors)


T = TypeVar("T")

DataWithConstraint = Tuple[Any, Optional[Constraints]]


class Deserializer(DeserializationVisitor[DataWithConstraint, Any],):
    def __init__(
        self,
        conversions: Optional[Conversions],
        coercer: Coercer,
        additional_properties: bool,
        default_fallback: bool,
    ):
        super().__init__(conversions)
        self.coercer = coercer
        self.additional_properties = additional_properties
        self.default_fallback = default_fallback

    def annotated(
        self, cls: AnyType, annotations: Sequence[Any], data2: DataWithConstraint
    ):
        data, constraints = data2
        validators: Optional[Sequence[Validator]] = None
        # Highest schema is the last annotations
        for annotation in reversed(annotations):
            if annotation is Skip:
                raise Skipped()
            if isinstance(annotation, Schema):
                if constraints is None:
                    constraints = annotation.constraints
                else:
                    constraints = constraints.merge(annotation.constraints)
            if isinstance(annotation, ValidatorsMetadata):
                validators = annotation.validators
        result = self.visit(cls, (data, constraints))
        return validate(result, validators) if validators is not None else result

    def any(self, data2: DataWithConstraint):
        return data2[0]

    def collection(
        self, cls: Type[Iterable], value_type: AnyType, data2: DataWithConstraint
    ):
        data, constraints = data2
        data = self.coercer(list, data)
        elts = []
        errors: Dict[ErrorKey, ValidationError] = OrderedDict()
        for i, elt in enumerate(data):
            try:
                elts.append(self.visit(value_type, (elt, None)))
            except ValidationError as err:
                errors[i] = err
        validate_with_errors(data, constraints, errors)
        return elts if cls is LIST_TYPE else COLLECTION_TYPES[cls](elts)

    def dataclass(self, cls: Type, data2: DataWithConstraint):
        assert is_dataclass(cls)
        data, constraints = data2
        if constraints is not None:
            constraints = constraints.merge(get_constraints(cls))
        else:
            constraints = get_constraints(cls)
        data = self.coercer(dict, data)
        values: Dict[str, Any] = {}
        aliases: List[str] = []
        errors: List[ErrorMsg] = []
        field_errors: Dict[ErrorKey, ValidationError] = OrderedDict()

        def set_field(field: Field, value: Any, alias: Optional[str] = None):
            try:
                result = field.deserialization_method(
                    self, field.deserialization_type, (value, field.constraints)
                )
            except ValidationError as err:
                if field.default and (self.default_fallback or field.default_fallback):
                    pass
                elif alias is not None:
                    field_errors[alias] = err
                else:
                    errors.extend(err.messages)
                    field_errors.update(err.children)
            else:
                values[field.name] = result

        (
            fields,
            merged_fields,
            pattern_fields,
            additional_field,
        ) = get_deserialization_fields(cls)
        for field in fields:
            alias = field.alias
            if alias in data:
                aliases.append(alias)
                set_field(field, data[alias], alias)
            elif field.default:
                if field.deserialization_required_by:
                    requiring = field.deserialization_required_by & data.keys()
                    if requiring:
                        field_errors[alias] = ValidationError(
                            [f"missing property (required by {sorted(requiring)})"]
                        )
            else:
                field_errors[alias] = ValidationError(["missing property"])
        for merged_alias, field in merged_fields:
            merged_alias = merged_alias & data.keys()
            aliases.extend(merged_alias)
            set_field(field, {alias: data[alias] for alias in merged_alias})
        if len(data) != len(aliases):
            remain = data.keys() - set(aliases)
            for pattern, field in pattern_fields:
                if pattern is ...:
                    pattern = infer_pattern(field)
                assert isinstance(pattern, Pattern)
                matched = {key: data[key] for key in remain if pattern.match(key)}
                remain -= matched.keys()
                set_field(field, matched)
            if additional_field is not None:
                set_field(additional_field, {key: data[key] for key in remain})
            elif remain and not self.additional_properties:
                for key in sorted(remain):
                    field_errors[key] = ValidationError(["unexpected property"])
        else:
            for _, field in pattern_fields:
                set_field(field, {})
            if additional_field is not None:
                set_field(additional_field, {})
        error: Optional[ValidationError] = None
        if field_errors or errors:
            error = ValidationError(errors, field_errors)
        if constraints is not None:
            try:
                constraints.validate(data)
            except ValidationError as err:
                error = merge_errors(error, err)
        init: Dict[str, Any] = {}
        post_init_fields = get_post_init_fields(cls)
        if post_init_fields:
            for field in post_init_fields:
                if field.name in values:
                    init[field.name] = values[field.name]
                elif field.name not in field_errors and field.default:
                    init[field.name] = get_default(field.base_field)
        # Don't keep validators when all dependencies are default
        validators = [v for v in get_validators(cls) if v.dependencies & values.keys()]
        if error:
            invalid_fields = field_errors.keys() | {
                field.name for field in fields if field.post_init
            }
            validators = [v for v in validators if not v.dependencies & invalid_fields]
            try:
                validate(ValidatorMock(cls, values), validators, **init)
            except ValidationError as err:
                error = merge_errors(error, err)
            raise error
        try:
            res = cls(**values)
        except (ValidationError, AssertionError):
            raise
        except TypeError as err:
            if str(err).startswith("__init__() got"):
                return self.unsupported(cls, data2)
            else:
                raise ValidationError([str(err)])
        except Exception as err:
            raise ValidationError([str(err)])
        validate(res, validators, **init)
        return res

    def enum(self, cls: Type[Enum], data2: DataWithConstraint):
        data, _ = data2
        assert _ is None
        try:
            return cls(data)
        except ValueError:
            return cls(self.literal([elt.value for elt in cls], data2))

    def literal(self, values: Sequence[Any], data2: DataWithConstraint):
        # Literal can contain Enum values and thus has to call visit too
        data, _ = data2
        assert _ is None
        if data in values:
            return data
        for value in values:
            try:
                if self.visit(type(value), data2) == value:
                    return value
            except Exception:
                continue
        allowed_values = [
            value if not isinstance(value, Enum) else value.value for value in values
        ]
        raise ValidationError([f"not one of {allowed_values}"])

    def mapping(
        self,
        cls: Type[Mapping],
        key_type: AnyType,
        value_type: AnyType,
        data2: DataWithConstraint,
    ):
        data, constraints = data2
        data = self.coercer(dict, data)
        items = {}
        errors: Dict[ErrorKey, ValidationError] = OrderedDict()
        for key, value in data.items():
            assert isinstance(key, str)
            try:
                new_key = self.visit(key_type, (key, None))
                items[new_key] = self.visit(value_type, (value, None))
            except ValidationError as err:
                errors[key] = err
        validate_with_errors(data, constraints, errors)
        return items if cls is DICT_TYPE else MAPPING_TYPES[cls](items)

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
        data2: DataWithConstraint,
    ):
        data, constraints = data2
        data = self.coercer(dict, data)
        if constraints is not None:
            constraints = constraints.merge(get_constraints(cls))
        else:
            constraints = get_constraints(cls)
        mapping: Dict[str, Any] = {}
        errors: Dict[ErrorKey, ValidationError] = OrderedDict()
        for key, cls in types.items():
            if key in data:
                try:
                    mapping[key] = self.visit(cls, (data[key], None))
                except ValidationError as err:
                    if key in defaults and self.default_fallback:
                        pass
                    else:
                        errors[key] = err
            elif key in defaults:
                pass
            else:
                errors[key] = ValidationError(["missing property"])
        if not self.additional_properties:
            for key in sorted(data.keys() - defaults.keys() - mapping.keys()):
                errors[key] = ValidationError(["unexpected property"])
        validate_with_errors(data, constraints, errors)
        return validate(cls(**mapping))

    def new_type(self, cls: AnyType, super_type: AnyType, data2: DataWithConstraint):
        data, constraints = data2
        if constraints is not None:
            constraints = constraints.merge(get_constraints(cls))
        else:
            constraints = get_constraints(cls)
        return validate(
            self.visit(super_type, (data, constraints)), get_validators(cls),
        )

    def primitive(self, cls: Type, data2: DataWithConstraint):
        data, constraints = data2
        data = self.coercer(cls, data)
        if constraints is not None and data is not None:
            constraints.validate(data)
        return data

    def subprimitive(self, cls: Type, superclass: Type, data2: DataWithConstraint):
        data, constraints = data2
        if constraints is not None:
            constraints = constraints.merge(get_constraints(cls))
        else:
            constraints = get_constraints(cls)
        return validate(cls(self.primitive(superclass, (data, constraints))))

    def tuple(self, types: Sequence[AnyType], data2: DataWithConstraint):
        data, constraints = data2
        data = self.coercer(list, data)
        ArrayConstraints(min_items=len(types), max_items=len(types)).validate(data)
        elts: List[Any] = []
        errors: Dict[ErrorKey, ValidationError] = OrderedDict()
        for i, (cls, elt) in enumerate(zip(types, data)):
            try:
                elts.append(self.visit(cls, (elt, None)))
            except ValidationError as err:
                errors[i] = err
        validate_with_errors(data, constraints, errors)
        return tuple(elts)

    def typed_dict(
        self,
        cls: Type,
        keys: Mapping[str, AnyType],
        total: bool,
        data2: DataWithConstraint,
    ):
        data, constraints = data2
        data = self.coercer(dict, data)
        if constraints is not None:
            constraints = constraints.merge(get_constraints(cls))
        else:
            constraints = get_constraints(cls)
        mapping: Dict[str, Any] = {}
        keys_in_dict = 0
        errors: Dict[ErrorKey, ValidationError] = OrderedDict()
        for key, value in data.items():
            assert isinstance(key, str)
            if key in keys:
                keys_in_dict += 1
                try:
                    mapping[key] = self.visit(keys[key], (value, None))
                except ValidationError as err:
                    errors[key] = err
            else:
                mapping[key] = value
        if total and keys_in_dict != len(keys):
            for key in keys:
                if key not in data:
                    errors[key] = ValidationError(["missing property"])
        validate_with_errors(data, constraints, errors)
        return validate(mapping, get_validators(cls))

    def union(self, alternatives: Sequence[AnyType], data2: DataWithConstraint):
        # Optional optimization
        data, _ = data2
        if data is None and alternatives[-1] is NoneType:
            return None
        error: Optional[ValidationError] = None
        for cls in alternatives:
            try:
                return self.visit(cls, data2)
            except Skipped:
                pass
            except ValidationError as err:
                error = merge_errors(error, err)
        raise error if error is not None else RuntimeError("Empty union")

    def visit_conversion(
        self, cls: Type, conversion: Deserialization, data2: DataWithConstraint
    ):
        assert conversion
        data, constraints = data2
        if constraints is not None:
            constraints = constraints.merge(get_constraints(cls))
        else:
            constraints = get_constraints(cls)
        data2 = data, constraints
        error: Optional[ValidationError] = None
        value: Any = ...
        conversions = self.conversions
        for cls_, (converter, self.conversions) in conversion.items():
            try:
                value = self.visit(cls_, data2)
                break
            except Skipped:
                raise TypeError("Deserialization type cannot be skipped")
            except ValidationError as err:
                error = merge_errors(error, err)
            finally:
                self.conversions = conversions
        else:
            assert error is not None
            raise error
        assert value is not ...
        try:
            return validate(converter(value))
        except (ValidationError, AssertionError):
            raise
        except Exception as err:
            raise ValidationError([str(err)])


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
    cls: Type[T],
    data: Any,
    *,
    conversions: Conversions = None,
    additional_properties: bool = None,
    coercion: Coercion = None,
    default_fallback: bool = None,
) -> T:
    if additional_properties is None:
        additional_properties = settings.additional_properties
    if coercion is None:
        coercion = settings.coercion
    if default_fallback is None:
        default_fallback = settings.default_fallback
    return Deserializer(
        conversions, get_coercer(coercion), additional_properties, default_fallback
    ).visit(cls, (data, None))
