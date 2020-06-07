from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Tuple, Type, TypeVar

from apischema.conversion import Converter, OutputVisitorMixin
from apischema.dataclasses import Field, get_output_fields_raw
from apischema.fields import get_fields_set
from apischema.types import AnyType, PRIMITIVE_TYPES
from apischema.visitor import NOT_CUSTOM, Unsupported

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)


def dataclass_field_value(obj: Any, field: Field):
    assert is_dataclass(obj)
    value = getattr(obj, field.name)
    if field.output_converter is not None:
        value = field.output_converter(value)
    return value


T = TypeVar("T", bound=Any)


class ToData(OutputVisitorMixin[Any, Any]):
    def __init__(self, conversions: Mapping[Type, Type], exclude_unset: bool):
        super().__init__(conversions)
        self.exclude_unset = exclude_unset

    def _custom(self, cls: Type, custom: Tuple[Type, Converter], obj: Any) -> Any:
        _, converter = custom
        return self.visit(converter(obj))

    def visit(self, obj: T) -> Any:
        cls = type(obj)
        if cls in PRIMITIVE_TYPES_SET:
            return obj
        if cls is dict:
            return {self.visit(key): self.visit(value) for key, value in obj.items()}
        if cls in {list, tuple, set, frozenset}:
            return [self.visit(elt) for elt in obj]
        custom = self.custom(cls, obj)
        if custom is not NOT_CUSTOM:
            return custom
        if is_dataclass(cls):
            fields, properties_fields = get_output_fields_raw(cls)
            if self.exclude_unset:
                fields_set = get_fields_set(obj)
                fields = [f for f in fields if f.name in fields_set]
            result = {
                field.alias: self.visit(dataclass_field_value(obj, field))
                for field in fields
            }
            for field in properties_fields:
                value = self.visit(dataclass_field_value(obj, field))
                result.update(value)
            return result
        if issubclass(cls, Enum):
            return obj.value
        if isinstance(obj, PRIMITIVE_TYPES):
            return obj
        if isinstance(obj, Mapping):
            return {self.visit(key): self.visit(value) for key, value in obj.items()}
        if isinstance(obj, Iterable):
            return [self.visit(elt) for elt in obj]
        raise Unsupported(cls)


def to_data(
    obj: Any, *, conversions: Mapping[Type, AnyType] = None, exclude_unset: bool = True,
) -> Any:
    return ToData(conversions or {}, exclude_unset).visit(obj)
