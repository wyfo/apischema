__all__ = ["serialize"]
from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Collection, Mapping, Optional, Type, TypeVar

from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import (
    Serialization,
    SerializationVisitor,
)
from apischema.dataclasses.cache import get_aggregate_serialization_fields
from apischema.fields import FIELDS_SET_ATTR, fields_set
from apischema.types import AnyType, PRIMITIVE_TYPES

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)
COLLECTION_TYPE_SET = {list, tuple, set, frozenset}


T = TypeVar("T", bound=Any)


class Serializer(SerializationVisitor[Any, Any]):
    def __init__(self, conversions: Optional[Conversions], exclude_unset: bool):
        super().__init__(conversions)
        self.exclude_unset = exclude_unset

    def visit(self, cls: AnyType, obj):
        return self.visit2(obj)

    def visit2(self, obj):
        cls = type(obj)
        # inline to be faster
        if cls in PRIMITIVE_TYPES_SET:
            return obj
        if cls in COLLECTION_TYPE_SET:
            return [self.visit2(elt) for elt in obj]
        if cls is dict:
            return {self.visit2(key): self.visit2(value) for key, value in obj.items()}
        return self.visit_not_builtin(cls, obj)

    def visit_conversion(self, _, conversion: Serialization, obj):
        conversions = self.conversions
        _, (converter, self.conversions) = conversion
        try:
            return self.visit2(converter(obj))
        finally:
            self.conversions = conversions

    def visit_not_conversion(self, cls: Type, obj):
        assert cls is type(obj)
        if is_dataclass(cls):
            fields, aggregate_fields = get_aggregate_serialization_fields(cls)
            if self.exclude_unset and hasattr(obj, FIELDS_SET_ATTR):
                fields_set_ = fields_set(obj)
                fields = [f for f in fields if f.name in fields_set_]
                aggregate_fields = [
                    f for f in aggregate_fields if f.name in fields_set_
                ]
            result = {}
            # properties before normal fields to avoid overloading a field with property
            for field in aggregate_fields:
                result.update(
                    field.serialization_method(self, getattr(obj, field.name))
                )
            for field in fields:
                result[field.alias] = field.serialization_method(
                    self, getattr(obj, field.name)
                )
            return result
        if issubclass(cls, Enum):
            return obj.value
        if isinstance(obj, PRIMITIVE_TYPES):
            return obj
        if isinstance(obj, Mapping):
            return {self.visit2(key): self.visit2(value) for key, value in obj.items()}
        if isinstance(obj, Collection):
            return [self.visit2(elt) for elt in obj]
        if issubclass(cls, tuple) and hasattr(cls, "_fields"):
            return {f: self.visit2(getattr(obj, f)) for f in obj._fields}
        return self.unsupported(cls, obj)


NO_OBJ = object()


def serialize(
    obj: Any, *, conversions: Conversions = None, exclude_unset: bool = True,
) -> Any:
    return Serializer(conversions, exclude_unset).visit(type(obj), obj)
