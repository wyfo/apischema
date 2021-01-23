from dataclasses import is_dataclass
from enum import Enum
from typing import (
    Any,
    Callable,
    Collection,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
)

from apischema import settings
from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.conversions import Conversions, to_hashable_conversions
from apischema.conversions.dataclass_models import DataclassModel
from apischema.conversions.visitor import SerializationVisitor
from apischema.dataclass_utils import (
    dataclass_types_and_fields,
    get_alias,
    get_field_conversion,
)
from apischema.fields import FIELDS_SET_ATTR, fields_set
from apischema.metadata.keys import SKIP_METADATA, check_metadata, is_aggregate_field
from apischema.serialization.serialized_methods import get_serialized_methods
from apischema.types import COLLECTION_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES
from apischema.utils import OperationKind, Undefined
from apischema.visitor import Unsupported

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)
COLLECTION_TYPE_SET = set(COLLECTION_TYPES)
MAPPING_TYPE_SET = set(MAPPING_TYPES)

SerializationMethod = Callable[[Any, bool, Callable], Any]


@cache
def serialization_fields(
    cls: Type, aliaser: Aliaser
) -> Tuple[
    Sequence[Tuple[str, str, SerializationMethod]],
    Sequence[Tuple[str, SerializationMethod]],
    Sequence[Tuple[str, SerializationMethod]],
]:
    types, fields, _ = dataclass_types_and_fields(cls)  # type: ignore
    normal_fields, aggregate_fields, serialized_fields = [], [], []
    for field in fields:
        if SKIP_METADATA in field.metadata:
            continue
        check_metadata(field)
        field_type, conversion = get_field_conversion(
            field, types[field.name], OperationKind.SERIALIZATION
        )
        method: Callable
        if conversion is not None:
            # method could be optimized when identity is used, but it's a lot more lines
            # for an unnecessary thing
            def method(
                obj: Any,
                exc_unset: bool,
                _serialize: Callable,
                conversions=conversion.conversions,  # type: ignore
                converter=conversion.converter,  # type: ignore
                exclude_unset=conversion.exclude_unset,  # type: ignore
            ) -> Any:
                if exclude_unset is not None:
                    exc_unset = exclude_unset
                return _serialize(converter(obj), exc_unset, conversions=conversions)

        elif field_type in PRIMITIVE_TYPES_SET:

            def method(obj: Any, exc_unset: bool, _serialize: Callable):
                return obj

        else:

            def method(obj: Any, exc_unset: bool, _serialize: Callable):
                return _serialize(obj, exc_unset)

        if is_aggregate_field(field):
            aggregate_fields.append((field.name, method))
        else:
            normal_fields.append((field.name, aliaser(get_alias(field)), method))
    for name, (serialized, _) in get_serialized_methods(cls).items():

        def method(
            obj: Any,
            exc_unset: bool,
            _serialize: Callable,
            func=serialized.func,
            conversions=serialized.conversions,
        ) -> Any:
            res = func(obj)
            return (
                res
                if res is Undefined
                else _serialize(res, exc_unset, conversions=conversions)
            )

        serialized_fields.append((aliaser(name), method))

    return normal_fields, aggregate_fields, serialized_fields


get_conversions = cache(SerializationVisitor.get_conversions)


def serialize(
    obj: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
    exclude_unset: bool = None,
) -> Any:
    if aliaser is None:
        aliaser = settings.aliaser()
    if exclude_unset is None:
        exclude_unset = settings.exclude_unset
    conversions = to_hashable_conversions(conversions)

    def _serialize(
        obj: Any,
        exc_unset: bool,
        *,
        conversions: Optional[Conversions] = None,
    ) -> Any:
        assert aliaser is not None
        cls = obj.__class__
        if cls in PRIMITIVE_TYPES_SET:
            return obj
        if cls in COLLECTION_TYPE_SET:
            return [_serialize(elt, exc_unset, conversions=conversions) for elt in obj]
        if cls in MAPPING_TYPE_SET:
            return {
                _serialize(key, exc_unset, conversions=conversions): _serialize(
                    value, exc_unset, conversions=conversions
                )
                for key, value in obj.items()
            }
        conversion = get_conversions(cls, conversions)
        if conversion is not None:
            if conversion.exclude_unset is not None:
                exc_unset = conversion.exclude_unset
            if isinstance(conversion.target, DataclassModel):
                cls = conversion.target.dataclass
            else:
                return _serialize(
                    conversion.converter(obj),  # type: ignore
                    exc_unset,
                    conversions=conversion.conversions,
                )
        if is_dataclass(cls):
            fields, aggregate_fields, serialized_fields = serialization_fields(
                cls, aliaser
            )
            if exclude_unset and hasattr(obj, FIELDS_SET_ATTR):
                fields_set_ = fields_set(obj)
                fields = [
                    (name, alias, method)
                    for (name, alias, method) in fields
                    if name in fields_set_
                ]
                aggregate_fields = [
                    (name, method)
                    for (name, method) in aggregate_fields
                    if name in fields_set_
                ]
            result = {}
            # properties before normal fields to avoid overloading a field with property
            for name, method in aggregate_fields:
                attr = getattr(obj, name)
                result.update(method(attr, exc_unset, _serialize))  # type: ignore
            for name, alias, method in fields:
                attr = getattr(obj, name)
                if attr is not Undefined:
                    result[alias] = method(attr, exc_unset, _serialize)  # type: ignore
            for alias, method in serialized_fields:
                res = method(obj, exc_unset, _serialize)
                if res is not Undefined:
                    result[alias] = res
            return result
        if obj is Undefined:
            raise Unsupported(cls)
        if issubclass(cls, Enum):
            return _serialize(obj.value, exc_unset)
        if isinstance(obj, PRIMITIVE_TYPES):
            return obj
        if isinstance(obj, Mapping):
            return {
                _serialize(key, exc_unset): _serialize(value, exc_unset)
                for key, value in obj.items()
            }
        if issubclass(cls, tuple) and hasattr(cls, "_fields"):
            result = {}
            for field_name in obj._fields:
                attr = getattr(obj, field_name)
                if attr is not Undefined:
                    result[aliaser(field_name)] = attr
            for name, (serialized, _) in get_serialized_methods(cls).items():
                res = serialized.func(obj)
                if res is not Undefined:
                    result[aliaser(name)] = _serialize(
                        res, exc_unset, conversions=serialized.conversions
                    )
            return result
        if isinstance(obj, Collection):
            return [_serialize(elt, exc_unset) for elt in obj]
        raise Unsupported(cls)

    return _serialize(obj, exclude_unset, conversions=conversions)
