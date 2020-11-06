__all__ = ["serialize"]

from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import partial
from typing import Any, Callable, Collection, Mapping, Sequence, Tuple, Type

from apischema.cache import cache
from apischema.conversions.metadata import get_field_conversions
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import SerializationVisitor
from apischema.dataclass_utils import get_alias
from apischema.fields import FIELDS_SET_ATTR, fields_set
from apischema.metadata.keys import check_metadata, is_aggregate_field
from apischema.types import COLLECTION_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES
from apischema.visitor import Unsupported, dataclass_types_and_fields

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)
COLLECTION_TYPE_SET = set(COLLECTION_TYPES.values())
MAPPING_TYPE_SET = set(MAPPING_TYPES.values())


try:
    from apischema.typing import Protocol

    class SerializerMethod(Protocol):
        def __call__(self, obj: Any, *exclude_unset: bool) -> Any:
            ...


except ImportError:
    SerializerMethod = Callable  # type: ignore


@dataclass
class SerializationField:
    name: str
    method: SerializerMethod


@cache
def serialization_fields(
    cls: Type,
) -> Tuple[Sequence[Tuple[str, SerializationField]], Sequence[SerializationField]]:
    types, fields, _ = dataclass_types_and_fields(cls)  # type: ignore
    normal_fields = []
    aggregate_fields = []
    for field in fields:
        check_metadata(field)
        field_type = types[field.name]
        method: Callable
        conversions = get_field_conversions(field, field_type)
        if conversions is not None:
            if conversions.deserializer is None:
                method = partial(serialize, conversions=conversions.serialization)
            else:
                _, (converter, sub_conversions) = conversions.serialization_conversion(
                    field_type
                )

                def method(obj: Any, *, exclude_unset: bool) -> Any:
                    return serialize(
                        converter(obj),
                        conversions=sub_conversions,
                        exclude_unset=exclude_unset,
                    )

        elif field_type in PRIMITIVE_TYPES_SET:
            method = lambda obj, *, exclude_unset: obj  # noqa E731
        else:
            method = serialize
        field2 = SerializationField(field.name, method)
        if is_aggregate_field(field):
            aggregate_fields.append(field2)
        else:
            normal_fields.append((get_alias(field), field2))
    return normal_fields, aggregate_fields


def serialize(
    obj: Any, *, conversions: Conversions = None, exclude_unset: bool = True
) -> Any:
    cls = obj.__class__
    if cls in PRIMITIVE_TYPES_SET:
        return obj
    if cls in COLLECTION_TYPE_SET:
        return [
            serialize(elt, conversions=conversions, exclude_unset=exclude_unset)
            for elt in obj
        ]
    if cls in MAPPING_TYPE_SET:
        return {
            serialize(
                key, conversions=conversions, exclude_unset=exclude_unset
            ): serialize(value, conversions=conversions, exclude_unset=exclude_unset)
            for key, value in obj.items()
        }
    conversion = SerializationVisitor.is_conversion(cls, conversions)
    if conversion is not None:
        _, (converter, sub_conversions) = conversion
        # TODO Maybe add exclude_unset parameter to serializers
        return serialize(
            converter(obj), conversions=sub_conversions, exclude_unset=exclude_unset
        )
    if is_dataclass(cls):
        fields, aggregate_fields = serialization_fields(cls)
        if exclude_unset and hasattr(obj, FIELDS_SET_ATTR):
            fields_set_ = fields_set(obj)
            fields = [(a, f) for (a, f) in fields if f.name in fields_set_]
            aggregate_fields = [f for f in aggregate_fields if f.name in fields_set_]
        result = {}
        # properties before normal fields to avoid overloading a field with property
        for field in aggregate_fields:
            attr = getattr(obj, field.name)
            result.update(
                field.method(attr, exclude_unset=exclude_unset)  # type: ignore
            )
        for alias, field in fields:
            attr = getattr(obj, field.name)
            result[alias] = field.method(  # type: ignore
                attr, exclude_unset=exclude_unset
            )
        return result
    if issubclass(cls, Enum):
        return serialize(obj.value, exclude_unset=exclude_unset)
    if isinstance(obj, PRIMITIVE_TYPES):
        return obj
    if isinstance(obj, Mapping):
        return {
            serialize(key, exclude_unset=exclude_unset): serialize(
                value, exclude_unset=exclude_unset
            )
            for key, value in obj.items()
        }
    if isinstance(obj, Collection):
        return [serialize(elt, exclude_unset=exclude_unset) for elt in obj]
    if issubclass(cls, tuple) and hasattr(cls, "_fields"):
        return {
            f: serialize(getattr(obj, f), exclude_unset=exclude_unset)
            for f in obj._fields
        }
    raise Unsupported(cls)
