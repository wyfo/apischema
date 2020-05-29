from enum import Enum
from typing import Any, Dict, Mapping, Tuple, Type, TypeVar

from dataclasses import is_dataclass

from apischema.conversion import Converter, OutputVisitorMixin
from apischema.dataclasses import Field, get_output_fields_raw
from apischema.fields import get_fields_set
from apischema.types import PRIMITIVE_TYPE
from apischema.visitor import NOT_CUSTOM


class ToData(OutputVisitorMixin[Any, Any]):
    def __init__(self, conversions: Mapping[Type, Type], exclude_unset: bool):
        super().__init__(conversions)
        self.exclude_unset = exclude_unset

    def _custom(self, cls: Type, custom: Tuple[Type, Converter], obj: Any) -> Any:
        _, converter = custom
        return self.visit(converter(obj))

    def dataclass(self, cls: Type, obj: Any) -> Any:
        result: Dict[str, Any] = {}

        def field_value(field: Field):
            value = getattr(obj, field.name)
            if field.output_converter is not None:
                value = field.output_converter(value)
            return value

        fields, properties_fields = get_output_fields_raw(cls)
        if self.exclude_unset:
            fields_set = get_fields_set(obj)
            fields = [f for f in fields if f.name in fields_set]
        for field in fields:
            value = self.visit(field_value(field))
            result[field.alias] = value
        for field in properties_fields:
            value = self.visit(field_value(field))
            result.update(value)
        return result

    def visit(self, obj: Any) -> Any:
        cls = type(obj)
        if cls in PRIMITIVE_TYPE:
            return obj
        if cls is dict:
            return {self.visit(key): self.visit(value) for key, value in obj.items()}
        if cls in {list, tuple, set, frozenset}:
            return [self.visit(elt) for elt in obj]
        custom = self.custom(cls, obj)
        if custom is not NOT_CUSTOM:
            return custom
        if issubclass(cls, Enum):
            return obj.value
        if is_dataclass(cls):
            return self.dataclass(cls, obj)
        return obj


T = TypeVar("T")


def to_data(
    obj: Any, *, conversions: Mapping[Type, Type] = None, exclude_unset: bool = True,
) -> Any:
    return ToData(conversions or {}, exclude_unset).visit(obj)
