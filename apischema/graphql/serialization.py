__all__ = ["serialize"]

from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Collection, Mapping

from apischema.aliases import Aliaser
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import SerializationVisitor
from apischema.types import COLLECTION_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES
from apischema.visitor import Unsupported

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)
COLLECTION_TYPE_SET = set(COLLECTION_TYPES)
MAPPING_TYPE_SET = set(MAPPING_TYPES)


def serialize(
    obj: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
) -> Any:
    assert aliaser is not None
    cls = obj.__class__
    if cls in PRIMITIVE_TYPES_SET:
        return obj
    if cls in COLLECTION_TYPE_SET:
        return [serialize(elt, conversions=conversions) for elt in obj]
    if cls in MAPPING_TYPE_SET:
        return {
            serialize(key, conversions=conversions): serialize(
                value, conversions=conversions
            )
            for key, value in obj.items()
        }
    target = None
    if conversions is not None:
        try:
            target = conversions[cls]
        except KeyError:
            pass
    conversion = SerializationVisitor._is_conversion(cls, target)
    if conversion is not None:
        _, (converter, sub_conversions) = conversion
        return serialize(converter(obj), conversions=sub_conversions)
    if is_dataclass(cls):
        return obj
    if issubclass(cls, Enum):
        return serialize(obj.value)
    if isinstance(obj, PRIMITIVE_TYPES):
        return obj
    if isinstance(obj, Mapping):
        return {serialize(key): serialize(value) for key, value in obj.items()}
    if isinstance(obj, Collection):
        return [serialize(elt) for elt in obj]
    if issubclass(cls, tuple) and hasattr(cls, "_fields"):
        return obj
    raise Unsupported(cls)
