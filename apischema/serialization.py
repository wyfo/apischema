__all__ = ["serialize"]

from dataclasses import dataclass, is_dataclass
from enum import Enum
from typing import Any, Callable, Collection, Mapping, Optional, Sequence, Tuple, Type

from apischema import settings
from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.metadata import get_field_conversions
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import SerializationVisitor
from apischema.dataclass_utils import dataclass_types_and_fields, get_alias
from apischema.fields import FIELDS_SET_ATTR, fields_set
from apischema.metadata.keys import SKIP_METADATA, check_metadata, is_aggregate_field
from apischema.types import COLLECTION_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES
from apischema.visitor import Unsupported

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)
COLLECTION_TYPE_SET = set(COLLECTION_TYPES)
MAPPING_TYPE_SET = set(MAPPING_TYPES)


@dataclass
class SerializationField:
    name: str
    method: Callable[[Any, Callable], Any]


@cache
def serialization_fields(
    cls: Type, aliaser: Aliaser
) -> Tuple[Sequence[Tuple[str, SerializationField]], Sequence[SerializationField]]:
    types, fields, _ = dataclass_types_and_fields(cls)  # type: ignore
    normal_fields = []
    aggregate_fields = []
    for field in fields:
        if SKIP_METADATA in field.metadata:
            continue
        check_metadata(field)
        field_type = types[field.name]
        method: Callable
        conversions = get_field_conversions(field, field_type)
        if conversions is not None:
            if conversions.serializer is None:
                sub_conversions = conversions.serialization

                def method(obj: Any, _serialize: Callable) -> Any:
                    return _serialize(obj, conversions=sub_conversions)

            else:
                _, (converter, sub_conversions) = conversions.serialization_conversion(
                    field_type
                )

                def method(obj: Any, _serialize: Callable) -> Any:
                    return _serialize(converter(obj), conversions=sub_conversions)

        elif field_type in PRIMITIVE_TYPES_SET:
            method = lambda obj, _: obj  # noqa E731
        else:
            method = lambda obj, _serialize: _serialize(obj)  # noqa E731
        field2 = SerializationField(field.name, method)
        if is_aggregate_field(field):
            aggregate_fields.append(field2)
        else:
            normal_fields.append((aliaser(get_alias(field)), field2))
    return normal_fields, aggregate_fields


def serialize(
    obj: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
    exclude_unset: bool = True,
) -> Any:
    if aliaser is None:
        aliaser = settings.aliaser()
    is_conversion = SerializationVisitor._is_conversion

    def _serialize(
        obj: Any,
        *,
        conversions: Optional[Conversions] = None,
    ) -> Any:
        assert aliaser is not None
        cls = obj.__class__
        if cls in PRIMITIVE_TYPES_SET:
            return obj
        if cls in COLLECTION_TYPE_SET:
            return [_serialize(elt, conversions=conversions) for elt in obj]
        if cls in MAPPING_TYPE_SET:
            return {
                _serialize(key, conversions=conversions): _serialize(
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
        conversion = is_conversion(cls, target)
        if conversion is not None:
            _, (converter, sub_conversions) = conversion
            # TODO Maybe add exclude_unset parameter to serializers
            return _serialize(converter(obj), conversions=sub_conversions)
        if is_dataclass(cls):
            fields, aggregate_fields = serialization_fields(cls, aliaser)
            if exclude_unset and hasattr(obj, FIELDS_SET_ATTR):
                fields_set_ = fields_set(obj)
                fields = [(a, f) for (a, f) in fields if f.name in fields_set_]
                aggregate_fields = [
                    f for f in aggregate_fields if f.name in fields_set_
                ]
            result = {}
            # properties before normal fields to avoid overloading a field with property
            for field in aggregate_fields:
                attr = getattr(obj, field.name)
                result.update(field.method(attr, _serialize))  # type: ignore
            for alias, field in fields:
                attr = getattr(obj, field.name)
                result[alias] = field.method(attr, _serialize)  # type: ignore
            return result
        if issubclass(cls, Enum):
            return _serialize(obj.value)
        if isinstance(obj, PRIMITIVE_TYPES):
            return obj
        if isinstance(obj, Mapping):
            return {_serialize(key): _serialize(value) for key, value in obj.items()}
        if isinstance(obj, Collection):
            return [_serialize(elt) for elt in obj]
        if issubclass(cls, tuple) and hasattr(cls, "_fields"):
            return {aliaser(f): _serialize(getattr(obj, f)) for f in obj._fields}
        raise Unsupported(cls)

    return _serialize(obj, conversions=conversions)
