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
from apischema.conversions.dataclass_models import DataclassModelWrapper, get_model
from apischema.conversions.utils import Conversions
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
from apischema.utils import Operation, Undefined
from apischema.visitor import Unsupported

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)
COLLECTION_TYPE_SET = set(COLLECTION_TYPES)
MAPPING_TYPE_SET = set(MAPPING_TYPES)

SerializationMethod = Callable[[Any, Callable], Any]


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
        field_type = types[field.name]
        conversion_type, conversions, converter = get_field_conversion(
            field, field_type, Operation.SERIALIZATION
        )
        method: Callable
        if converter is not None:

            def method(
                obj: Any,
                _serialize: Callable,
                conversions=conversions,
                converter=converter,
            ) -> Any:
                return _serialize(converter(obj), conversions=conversions)

        elif conversions is not None:

            def method(
                obj: Any,
                _serialize: Callable,
                conversions=conversions,
            ) -> Any:
                return _serialize(obj, conversions=conversions)

        elif field_type in PRIMITIVE_TYPES_SET:

            def method(obj: Any, _):
                return obj

        else:

            def method(obj: Any, _serialize: Callable):
                return _serialize(obj)

        if is_aggregate_field(field):
            aggregate_fields.append((field.name, method))
        else:
            normal_fields.append((field.name, aliaser(get_alias(field)), method))
    for name, serialized in get_serialized_methods(cls).items():

        def method(
            obj: Any,
            _serialize: Callable,
            func=serialized.func,
            conversions=serialized.conversions,
        ) -> Any:
            res = func(obj)
            return res if res is Undefined else _serialize(res, conversions=conversions)

        serialized_fields.append((aliaser(name), method))

    return normal_fields, aggregate_fields, serialized_fields


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
            target, (converter, sub_conversions) = conversion
            if isinstance(target, DataclassModelWrapper):
                cls = get_model(target.cls, target.model)
            else:
                # TODO Maybe add exclude_unset parameter to serializers
                return _serialize(converter(obj), conversions=sub_conversions)
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
                result.update(method(attr, _serialize))  # type: ignore
            for name, alias, method in fields:
                attr = getattr(obj, name)
                if attr is not Undefined:
                    result[alias] = method(attr, _serialize)  # type: ignore
            for alias, method in serialized_fields:
                res = method(obj, _serialize)
                if res is not Undefined:
                    result[alias] = res
            return result
        if obj is Undefined:
            raise Unsupported(cls)
        if issubclass(cls, Enum):
            return _serialize(obj.value)
        if isinstance(obj, PRIMITIVE_TYPES):
            return obj
        if isinstance(obj, Mapping):
            return {_serialize(key): _serialize(value) for key, value in obj.items()}
        if issubclass(cls, tuple) and hasattr(cls, "_fields"):
            result = {}
            for field_name in obj._fields:
                attr = getattr(obj, field_name)
                if attr is not Undefined:
                    result[aliaser(field_name)] = attr
            for name, serialized in get_serialized_methods(cls).items():
                res = serialized.func(obj)
                if res is not Undefined:
                    result[aliaser(name)] = _serialize(
                        res, conversions=serialized.conversions
                    )
            return result
        if isinstance(obj, Collection):
            return [_serialize(elt) for elt in obj]
        raise Unsupported(cls)

    return _serialize(obj, conversions=conversions)
