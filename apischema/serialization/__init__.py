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
from apischema.conversions.conversions import (
    Conversions,
    ResolvedConversion,
    handle_container_conversions,
    resolve_conversions,
)
from apischema.conversions.dataclass_models import DataclassModel
from apischema.conversions.visitor import SerializationVisitor
from apischema.dataclass_utils import (
    dataclass_types_and_fields,
    get_alias,
    get_field_conversions,
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


@cache
def serialization_fields(
    cls: Type, aliaser: Aliaser
) -> Tuple[
    Sequence[Tuple[str, str, Optional[Conversions]]],
    Sequence[Tuple[str, Optional[Conversions]]],
    Sequence[Tuple[Callable[[Any], Any], str, Optional[Conversions]]],
]:
    types, fields, _ = dataclass_types_and_fields(cls)  # type: ignore
    normal_fields, aggregate_fields, serialized_fields = [], [], []
    for field in fields:
        if SKIP_METADATA in field.metadata:
            continue
        check_metadata(field)
        conversions = get_field_conversions(field, OperationKind.SERIALIZATION)
        if is_aggregate_field(field):
            aggregate_fields.append((field.name, conversions))
        else:
            normal_fields.append((field.name, aliaser(get_alias(field)), conversions))
    for name, (serialized, _) in get_serialized_methods(cls).items():
        serialized_fields.append(
            (serialized.func, aliaser(name), serialized.conversions)
        )

    return normal_fields, aggregate_fields, serialized_fields


@cache
def get_conversions(
    tp: Type, conversions: Optional[Conversions]
) -> Tuple[Optional[ResolvedConversion], bool]:
    return SerializationVisitor.get_conversions(tp, resolve_conversions(conversions))


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

    def _serialize(
        obj: Any,
        exc_unset: bool,
        conversions: Conversions = None,
    ) -> Any:
        assert aliaser is not None
        cls = obj.__class__
        conversion, dynamic = get_conversions(cls, conversions)
        if conversion is not None:
            if conversion.exclude_unset is not None:
                exc_unset = conversion.exclude_unset
            if isinstance(conversion.target, DataclassModel):
                cls = conversion.target.dataclass
            else:
                return _serialize(
                    conversion.converter(obj),  # type: ignore
                    exc_unset,
                    handle_container_conversions(
                        conversion.target,
                        conversion.sub_conversions,
                        conversions,
                        dynamic,
                    ),
                )
        if cls in PRIMITIVE_TYPES_SET:
            return obj
        if cls in COLLECTION_TYPE_SET:
            return [_serialize(elt, exc_unset, conversions) for elt in obj]
        if cls in MAPPING_TYPE_SET:
            return {
                _serialize(key, exc_unset, conversions): _serialize(
                    value, exc_unset, conversions
                )
                for key, value in obj.items()
            }
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
            for name, conv in aggregate_fields:
                result.update(_serialize(getattr(obj, name), exc_unset, conv))
            for name, alias, conv in fields:
                attr = getattr(obj, name)
                if attr is not Undefined:
                    result[alias] = _serialize(attr, exc_unset, conv)
            for func, alias, conv in serialized_fields:
                res = func(obj)
                if res is not Undefined:
                    result[alias] = _serialize(res, exc_unset, conv)
            return result
        if obj is Undefined:
            raise Unsupported(cls)
        if issubclass(cls, Enum):
            return _serialize(obj.value, exc_unset)
        if isinstance(obj, PRIMITIVE_TYPES):
            return obj
        if isinstance(obj, Mapping):
            return {
                _serialize(key, exc_unset, conversions): _serialize(
                    value, exc_unset, conversions
                )
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
                        res, exc_unset, serialized.conversions
                    )
            return result
        if isinstance(obj, Collection):
            return [_serialize(elt, exc_unset, conversions) for elt in obj]
        raise Unsupported(cls)

    return _serialize(obj, exclude_unset, conversions)
