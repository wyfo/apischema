from collections.abc import Collection as Collection_
from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Callable, Collection, Mapping, Optional, Type, TypeVar

from apischema import settings
from apischema.aliases import AliasedStr, Aliaser
from apischema.cache import cache
from apischema.conversions.conversions import (
    Conversions,
    HashableConversions,
    handle_container_conversions,
    resolve_conversions,
    to_hashable_conversions,
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
from apischema.types import PRIMITIVE_TYPES
from apischema.utils import OperationKind, Undefined, UndefinedType
from apischema.visitor import Unsupported

T = TypeVar("T")

SerializationMethod = Callable[[T, bool], Any]


def serialize_object(cls: Type[T], aliaser: Aliaser) -> SerializationMethod[T]:
    serialized_fields = [
        (aliaser(name), method.func, to_hashable_conversions(method.conversions))
        for name, (method, _) in get_serialized_methods(cls).items()
    ]
    if is_dataclass(cls):
        types, fields, _ = dataclass_types_and_fields(cls)  # type: ignore
        normal_fields, aggregate_fields = [], []
        for field in fields:
            if SKIP_METADATA in field.metadata:
                continue
            check_metadata(field)
            conversions = to_hashable_conversions(
                get_field_conversions(field, OperationKind.SERIALIZATION)
            )
            if is_aggregate_field(field):
                aggregate_fields.append((field.name, conversions))
            else:
                normal_fields.append(
                    (field.name, aliaser(get_alias(field)), conversions)
                )

        def method(obj: T, exc_unset: bool) -> Any:
            normal_fields2, aggregate_fields2 = normal_fields, aggregate_fields
            if exc_unset and hasattr(obj, FIELDS_SET_ATTR):
                fields_set_ = fields_set(obj)
                normal_fields2 = [
                    (name, alias, method)
                    for (name, alias, method) in normal_fields
                    if name in fields_set_
                ]
                aggregate_fields2 = [
                    (name, method)
                    for (name, method) in aggregate_fields
                    if name in fields_set_
                ]
            result = {}
            # aggregate before normal fields to avoid overloading a field
            # with an aggregate
            for name, conv in aggregate_fields2:
                attr = getattr(obj, name)
                result.update(
                    serialization_method(attr.__class__, conv, aliaser)(attr, exc_unset)
                )
            for name, alias, conv in normal_fields2:
                attr = getattr(obj, name)
                if attr is not Undefined:
                    result[alias] = serialization_method(attr.__class__, conv, aliaser)(
                        attr, exc_unset
                    )
            for alias, func, conv in serialized_fields:
                res = func(obj)
                if res is not Undefined:
                    result[alias] = serialization_method(res.__class__, conv, aliaser)(
                        res, exc_unset
                    )
            return result

        return method
    elif issubclass(cls, tuple) and hasattr(cls, "_fields"):
        tuple_fields = cls._fields  # type: ignore

        def method(obj: T, exc_unset: bool):
            result = {}
            for field_name in tuple_fields:
                attr = getattr(obj, field_name)
                if attr is not Undefined:
                    result[aliaser(field_name)] = serialization_method(
                        attr.__class__, None, aliaser
                    )(attr, exc_unset)
            for alias, func, conv in serialized_fields:
                res = func(obj)
                if res is not Undefined:
                    result[alias] = serialization_method(res.__class__, conv, aliaser)(
                        res, exc_unset
                    )
            return result

        return method
    else:
        raise NotImplementedError


def serialize_undefined(obj: Any, exc_unset: bool) -> Any:
    raise Unsupported(UndefinedType)


def serialization_method_factory(
    object_method: Callable[[Type[T], Aliaser], SerializationMethod[T]],
    undefined_method: SerializationMethod,
) -> Callable[
    [Type[T], Optional[HashableConversions], Aliaser], SerializationMethod[T]
]:
    @cache
    def get_method(
        cls: Type[T],
        conversions: Optional[HashableConversions],
        aliaser: Aliaser,
    ):
        if cls is UndefinedType:
            return undefined_method
        conversion, dynamic = SerializationVisitor.get_conversions(
            cls, resolve_conversions(conversions)
        )
        if conversion is not None:
            if isinstance(conversion.target, DataclassModel):
                return get_method(conversion.target.dataclass, None, aliaser)
            else:
                converter = conversion.converter
                sub_conversions = handle_container_conversions(
                    conversion.target, conversion.sub_conversions, conversions, dynamic
                )
                exclude_unset = conversion.exclude_unset

                def method(obj: T, exc_unset: bool) -> Any:
                    if exclude_unset is not None:
                        exc_unset = exclude_unset
                    converted = converter(obj)  # type: ignore
                    return get_method(converted.__class__, sub_conversions, aliaser)(
                        converted, exc_unset
                    )

                return method
        if issubclass(cls, AliasedStr):
            return lambda obj, _: aliaser(obj)
        if issubclass(cls, PRIMITIVE_TYPES):
            return lambda obj, _: obj
        if issubclass(cls, tuple) and hasattr(cls, "_fields"):
            return object_method(cls, aliaser)  # type: ignore
        if issubclass(cls, Mapping):
            return lambda obj, exc_unset: {
                get_method(key.__class__, conversions, aliaser)(
                    key, exc_unset
                ): get_method(value.__class__, conversions, aliaser)(value, exc_unset)
                for key, value in obj.items()
            }
        if issubclass(cls, Collection):
            return lambda obj, exc_unset: [
                get_method(elt.__class__, conversions, aliaser)(elt, exc_unset)
                for elt in obj
            ]
        if is_dataclass(cls):
            return object_method(cls, aliaser)
        if issubclass(cls, Enum):
            return lambda obj, exc_unset: get_method(
                obj.value.__class__, None, aliaser
            )(obj.value, exc_unset)
        raise Unsupported(cls)

    return get_method


serialization_method = serialization_method_factory(
    serialize_object, serialize_undefined
)


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
    if conversions is not None and isinstance(conversions, Collection_):
        conversions = tuple(conversions)
    return serialization_method(obj.__class__, conversions, aliaser)(obj, exclude_unset)
