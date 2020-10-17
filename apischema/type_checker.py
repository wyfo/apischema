from contextlib import contextmanager
from dataclasses import is_dataclass
from enum import Enum
from itertools import chain
from typing import (
    Any,
    Callable,
    Collection,
    ContextManager,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from apischema.dataclasses.cache import get_aggregate_serialization_fields
from apischema.fields import fields_set
from apischema.json_schema.constraints import ArrayConstraints, get_constraints
from apischema.json_schema.schema import Schema
from apischema.types import AnyType, Skip, Skipped
from apischema.typing import get_type_hints
from apischema.utils import type_name
from apischema.validation import get_validators, validate
from apischema.validation.errors import (
    ErrorKey,
    ErrorMsg,
    ValidationError,
    merge_errors,
)
from apischema.visitor import Visitor


def check_type(obj: Any, cls: AnyType):
    if not isinstance(obj, cls):
        raise ValidationError(
            [f"expected {type_name(cls)}, found type {type_name(type(obj))}"]
        )


@contextmanager
def catcher() -> Iterator[Callable[[ErrorKey], ContextManager]]:
    @contextmanager
    def catch(key: ErrorKey = None):
        try:
            yield
        except ValidationError as err:
            if key is not None:
                errors[key] = merge_errors(errors.get(key), err)
            else:
                msgs.extend(err.messages)

    msgs: List[ErrorMsg] = []
    errors: Dict[ErrorKey, ValidationError] = {}
    yield catch
    if errors:
        raise ValidationError(children=errors)


class TypeChecker(Visitor[Any, Any]):
    def __init__(self, validation: bool):
        super().__init__()
        self.validation = validation

    def annotated(self, cls: AnyType, annotations: Sequence[Any], obj):
        for annotation in reversed(annotations):
            if annotation is Skip:
                raise Skipped()
        self.visit(cls, obj)
        if self.validation:
            for annotation in reversed(annotations):
                if (
                    isinstance(annotation, Schema)
                    and annotation.constraints is not None
                    and isinstance(obj, annotation.constraints.valid_types)
                ):
                    annotation.constraints.validate(obj)

    def any(self, obj):
        pass

    def collection(self, cls: Type[Collection], value_type: AnyType, obj):
        check_type(obj, cls)
        errors: Dict[ErrorKey, ValidationError] = {}
        for i, elt in enumerate(obj):
            try:
                self.visit(value_type, elt)
            except ValidationError as err:
                errors[i] = err
        if errors:
            raise ValidationError(children=errors)

    def dataclass(self, cls: Type, obj):
        assert is_dataclass(cls)
        check_type(obj, cls)
        types = get_type_hints(cls)
        errors: Dict[ErrorKey, ValidationError] = {}
        fields, aggregate_fields = get_aggregate_serialization_fields(cls)
        fields_set_ = fields_set(obj)
        for field in chain(fields, aggregate_fields):
            if field.name not in fields_set_:
                continue
            try:
                attr = getattr(obj, field.name)
                self.visit(types[field.name], attr)
                if self.validation:
                    if field.constraints is not None and isinstance(
                        attr, field.constraints.valid_types
                    ):
                        field.constraints.validate(attr)
                    if field.validators:
                        validate(attr, field.validators)
            except ValidationError as err:
                errors[field.name] = err
        if errors:
            raise ValidationError(children=errors)
        if self.validation:
            validate(obj, [v for v in get_validators(cls) if not v.params])

    def enum(self, cls: Type[Enum], obj):
        check_type(obj, cls)

    def literal(self, values: Sequence[Any], obj):
        if obj not in values:
            raise ValidationError(f"value is not one of {values}")

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType, obj):
        check_type(obj, cls)
        errors: Dict[ErrorKey, ValidationError] = {}
        for k, v in obj.items():
            try:
                self.visit(key_type, k)
            except ValidationError as err:
                errors[k] = err
            try:
                self.visit(value_type, v)
            except ValidationError as err:
                errors[k] = merge_errors(errors.get(k), err)
        if errors:
            raise ValidationError(children=errors)

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
        obj,
    ):
        check_type(obj, cls)
        errors: Dict[ErrorKey, ValidationError] = {}
        for field, field_type in types.items():
            try:
                self.visit(field_type, getattr(obj, field))
            except ValidationError as err:
                errors[field] = err
        if errors:
            raise ValidationError(children=errors)
        if self.validation:
            validate(obj)

    def new_type(self, cls: AnyType, super_type: AnyType, obj):
        self.visit(super_type, obj)
        if self.validation:
            constraints = get_constraints(cls)
            if constraints is not None and isinstance(obj, constraints.valid_types):
                constraints.validate(obj)

    def primitive(self, cls: Type, obj):
        check_type(obj, cls)

    def subprimitive(self, cls: Type, superclass: Type, obj):
        check_type(obj, cls)
        if self.validation:
            constraints = get_constraints(cls)
            if constraints is not None:
                constraints.validate(obj)
            validate(obj)

    def tuple(self, types: Sequence[AnyType], obj):
        check_type(obj, tuple)
        ArrayConstraints(min_items=len(types), max_items=len(types)).validate(obj)
        errors: Dict[ErrorKey, ValidationError] = {}
        for (i, type_), elt in zip(enumerate(types), obj):
            try:
                self.visit(type_, elt)
            except ValidationError as err:
                errors[i] = err
        if errors:
            raise ValidationError(children=errors)

    def typed_dict(self, cls: Type, keys: Mapping[str, AnyType], total: bool, obj):
        check_type(obj, Mapping)
        errors: Dict[ErrorKey, ValidationError] = {}
        for key, type_ in keys.items():
            if key in obj:
                try:
                    self.visit(type_, obj[key])
                except ValidationError as err:
                    errors[key] = err
            elif total:
                errors[key] = ValidationError("missing property")
        if errors:
            raise ValidationError(children=errors)
        if self.validation:
            constraints = get_constraints(cls)
            if constraints is not None:
                constraints.validate(obj)
            validate(obj, get_validators(cls))

    def union(self, alternatives: Sequence[AnyType], obj):
        error: Optional[ValidationError] = None
        for cls in alternatives:
            try:
                return self.visit(cls, obj)
            except ValidationError as err:
                error = merge_errors(error, err)
        raise error if error is not None else RuntimeError("Empty union")

    def unsupported(self, cls: AnyType, obj):
        check_type(obj, getattr(cls, "__origin__", None) or cls)


T = TypeVar("T")


def check_types(cls: AnyType, obj: T, *, validate: bool = True) -> T:
    TypeChecker(validate).visit(cls, obj)
    return obj
