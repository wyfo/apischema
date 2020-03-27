from dataclasses import Field, InitVar, _FIELD, is_dataclass  # type: ignore
from enum import Enum
from re import Pattern
from typing import (Any, Callable, Dict, Iterable, List, Mapping, Optional,
                    Sequence, Tuple, Type, TypeVar)

from apischema.alias import ALIAS_METADATA
from apischema.conversion import (ConversionError, Converter, INPUT_METADATA,
                                  InputVisitorMixin)
from apischema.data.common_errors import bad_literal, wrong_type
from apischema.fields import has_default, init_fields
from apischema.ignore import Ignored
from apischema.properties import PROPERTIES_METADATA
from apischema.schema import Constraint, Schema
from apischema.schema.constraints import (ArrayConstraint, CONSTRAINT_METADATA,
                                          ObjectConstraint, get_constraint)
from apischema.types import ITERABLE_TYPES, MAPPING_TYPES
from apischema.typing import get_type_hints
from apischema.utils import distinct
from apischema.validation.errors import (ValidationError,
                                         build_from_errors, exception,
                                         merge)
from apischema.validation.mock import ValidatorMock
from apischema.validation.validator import (Validator, get_validators, validate)
from apischema.visitor import Visitor


def check_type(data: Any, expected: Type):
    if type(data) is not expected:
        raise ValidationError([wrong_type(type(data), expected)])


def validate_with_errors(data: Any, constraint: Optional[Constraint],
                         errors: Mapping[str, ValidationError]):
    if constraint is not None:
        try:
            constraint.validate(data)
        except ValidationError as err:
            raise ValidationError(err.messages, errors)
    if errors:
        raise ValidationError(children=errors)


To = TypeVar("To")
From = TypeVar("From")


def apply_converter(value: From, converter: Callable[[From], To]) -> To:
    try:
        result = converter(value)
    except ValidationError:
        raise
    except ConversionError as err:
        raise build_from_errors(err.errors)
    except Exception as err:
        raise ValidationError([exception(err)])
    validate(result)
    return result


DataWithConstraint = Tuple[Any, Optional[Constraint]]


class FromData(InputVisitorMixin[DataWithConstraint, Any],
               Visitor[DataWithConstraint, Any]):
    def __init__(self, additional_properties: bool):
        Visitor.__init__(self)  # type: ignore
        self.additional_properties = additional_properties

    def primitive(self, cls: Type, data2: DataWithConstraint):
        data, constraint = data2
        check_type(data, cls)
        if constraint is not None and data is not None:
            constraint.validate(data)
        return data

    def _union(self, alternatives: Iterable[Type], data2: DataWithConstraint
               ) -> Tuple[Any, int]:
        error: Optional[ValidationError] = None
        for i, cls in enumerate(alternatives):
            try:
                return self.visit(cls, data2), i
            except Ignored:
                pass
            except ValidationError as err:
                error = merge(error, err)
        raise error if error is not None else TypeError("Ignored Union")

    def union(self, alternatives: Sequence[Type], data2: DataWithConstraint):
        # Optional optimization
        if data2[0] is None and alternatives[1] is type(None):  # noqa
            return None
        return self._union(alternatives, data2)[0]

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 data2: DataWithConstraint):
        data, constraint = data2
        check_type(data, list)
        elts: List[value_type] = []  # type: ignore
        errors: Dict[str, ValidationError] = {}
        elt_constraint = None
        if constraint is not None:
            assert isinstance(constraint, ArrayConstraint)
            elt_constraint = constraint.items
        assert elt_constraint is None or isinstance(elt_constraint, Constraint)
        for i, elt in enumerate(data):
            try:
                elts.append(self.visit(value_type, (elt, elt_constraint)))
            except ValidationError as err:
                errors[str(i)] = err
        validate_with_errors(data, constraint, errors)
        return ITERABLE_TYPES[cls](elts)

    def mapping(self, cls: Type[Mapping], key_type: Type,  # type: ignore
                value_type: Type, data2: DataWithConstraint):
        data, constraint = data2
        check_type(data, dict)
        mapping: Dict[key_type, value_type] = {}  # type: ignore
        errors: Dict[str, ValidationError] = {}
        prop_constraint = None
        if constraint is not None:
            assert isinstance(constraint, ObjectConstraint)
            prop_constraint = constraint.additional_properties
        for key, value in data.items():
            assert isinstance(key, str)
            try:
                new_key = self.visit(key_type, (key, None))
                mapping[new_key] = self.visit(value_type,
                                              (value, prop_constraint))
            except ValidationError as err:
                errors[key] = err
        validate_with_errors(data, constraint, errors)
        return MAPPING_TYPES[cls](mapping)

    def typed_dict(self, cls: Type, keys: Mapping[str, Type],
                   total: bool, data2: DataWithConstraint):
        data, constraint = data2
        check_type(data, dict)
        constraint = constraint or get_constraint(cls)
        mapping: Dict[str, Any] = {}
        keys_in_dict = 0
        errors: Dict[str, ValidationError] = {}
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
                    errors[key] = ValidationError(["missing key"])
        validate_with_errors(data, constraint, errors)
        return mapping

    def tuple(self, types: Sequence[Type], data2: DataWithConstraint):
        data, constraint = data2
        check_type(data, list)
        ArrayConstraint(min_items=len(types),
                        max_items=len(types)).validate(data)
        elts: List[Any] = []
        errors: Dict[str, ValidationError] = {}
        elt_constraints = None
        if constraint is not None:
            assert isinstance(constraint, ArrayConstraint)
            elt_constraints = constraint.items
        for i, (cls, elt) in enumerate(zip(types, data)):
            elt_constraint: Optional[Constraint]
            if elt_constraints is None:
                elt_constraint = None
            elif isinstance(elt_constraints, Sequence):
                elt_constraint = elt_constraints[i]
            else:
                elt_constraint = elt_constraints
            try:
                elts.append(self.visit(cls, (elt, elt_constraint)))
            except ValidationError as err:
                errors[str(i)] = err
        validate_with_errors(data, constraint, errors)
        return tuple(elts)

    def literal(self, values: Sequence[Any], data2: DataWithConstraint):
        # Literal can contain Enum values and thus has to call visit too
        assert data2[1] is None
        for cls in distinct(map(type, values)):
            try:
                value = self.visit(cls, data2)
            except ValidationError:
                continue
            if value in values:
                return value
        raise ValidationError([bad_literal(data2[0], values)])

    def _custom(self, cls: Type, custom: Dict[Type, Converter],
                data2: DataWithConstraint):
        data, constraint = data2
        constraint = constraint or get_constraint(cls)
        types = list(custom)
        value, index = self._union(types, (data, constraint))
        return apply_converter(value, custom[types[index]])

    def dataclass(self, cls: Type, data2: DataWithConstraint):
        assert is_dataclass(cls)
        data, constraint = data2
        constraint = constraint or get_constraint(cls)
        check_type(data, dict)
        types = get_type_hints(cls)
        values: Dict[str, Any] = {}
        default: Dict[str, Field] = {}
        init: Dict[str, Any] = {}
        aliases: List[str] = []
        additional_field: Optional[Field] = None
        pattern_fields: List[Field] = []
        field_errors: Dict[str, ValidationError] = {}

        def set_field(field: Field, value: Any, alias: str):
            constraint = field.metadata.get(CONSTRAINT_METADATA)
            try:
                if INPUT_METADATA in field.metadata:
                    param, converter = field.metadata[INPUT_METADATA]
                    tmp = self.visit(param, (value, constraint))
                    res = apply_converter(tmp, converter)
                else:
                    cls = types[field.name]
                    if isinstance(cls, InitVar):
                        cls = cls.type  # type: ignore
                    res = self.visit(cls, (value, constraint))
            except ValidationError as err:
                field_errors[alias] = err
            else:
                if field._field_type is _FIELD:  # type: ignore
                    values[field.name] = res
                else:
                    init[field.name] = res

        for field in init_fields(cls):
            metadata = field.metadata
            if PROPERTIES_METADATA in metadata:
                if metadata[PROPERTIES_METADATA] is None:
                    if additional_field is not None:
                        raise TypeError("Multiple additional_properties")
                    additional_field = field
                else:
                    pattern_fields.append(field)
                continue
            alias = metadata.get(ALIAS_METADATA, field.name)
            if alias in data:
                aliases.append(alias)
                set_field(field, data[alias], alias)
            elif has_default(field):
                default[field.name] = field
            else:
                field_errors[alias] = ValidationError(["missing field"])
        if len(data) != len(aliases):
            remain = set(data).difference(aliases)
        else:
            remain = set()
        for field in pattern_fields:
            pattern: Pattern = field.metadata[PROPERTIES_METADATA]
            matched = {key: data[key] for key in remain if pattern.match(key)}
            remain -= matched.keys()
            set_field(field, matched, f"/{pattern.pattern}/")
        if additional_field is not None:
            additional = {key: data[key] for key in remain}
            set_field(additional_field, additional, "<additionalProperties>")
        elif remain and not self.additional_properties:
            field_errors.update(
                (field, ValidationError(["field not allowed"]))
                for field in sorted(remain)
            )
        error: Optional[ValidationError] = None
        if field_errors:
            error = ValidationError(children=field_errors)
        if constraint is not None:
            assert isinstance(constraint, ObjectConstraint)
            assert constraint.additional_properties is None
            try:
                constraint.validate(data)
            except ValidationError as err:
                error = merge(error, err)
        validators: Iterable[Validator]
        if hasattr(cls, "__post_init__") or error:
            partial: List[Validator] = []
            whole: List[Validator] = []
            for val in get_validators(cls):
                if val.can_be_called(values.keys()):
                    partial.append(val)
                else:
                    whole.append(val)
            try:
                validate(ValidatorMock(cls, values, default), partial, **init)
            except ValidationError as err:
                error = merge(error, err)
            if error:
                raise error
            validators = whole
        else:
            validators = get_validators(cls)
        try:
            res = cls(**values, **init)
        except ValidationError:
            raise
        except Exception as err:
            raise ValidationError([exception(err)])
        validate(res, validators, **init)
        return res

    def enum(self, cls: Type[Enum], data2: DataWithConstraint):
        data, constraint = data2
        assert constraint is None
        try:
            return cls(data)
        except ValueError as err:
            raise ValidationError([str(err)])

    def new_type(self, cls: Type, super_type: Type, data2: DataWithConstraint):
        data, constraint = data2
        data2_ = data, constraint or get_constraint(cls)
        return self.visit(super_type, data2_)

    def any(self, data2: DataWithConstraint):
        return data2[0]

    def annotated(self, cls: Type, annotations: Sequence[Any],
                  data2: DataWithConstraint):
        if Ignored in annotations:
            raise Ignored()
        data, constraint = data2
        if constraint is None:
            for annotation in annotations:
                if isinstance(annotation, Schema):
                    constraint = annotation.constraint
                    break
        return self.visit(cls, (data, constraint))


T = TypeVar("T")


def from_data(data: Any, cls: Type[T], *, additional_properties: bool = False
              ) -> T:
    return FromData(additional_properties).visit(cls, (data, None))
