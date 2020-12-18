from collections import ChainMap
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Type, TypeVar, overload

from apischema.conversions.raw import to_raw_deserializer
from apischema.conversions.utils import (
    Conversions,
    Converter,
    check_converter,
)
from apischema.dataclass_utils import is_dataclass
from apischema.type_vars import resolve_type_vars
from apischema.types import AnyType, Metadata, MetadataMixin
from apischema.typing import get_args, get_origin
from apischema.utils import is_type_var


def handle_generic_field_type(
    field_type: AnyType, base: AnyType, other: AnyType, covariant: bool
) -> AnyType:
    contravariant = not covariant
    type_vars = None
    if is_type_var(base):
        type_vars = {base: field_type}
    if (
        get_origin(base) is not None
        and getattr(base, "__parameters__", ())
        and len(get_args(base)) == len(get_args(field_type))
        and not any(map(get_origin, get_args(base)))
        and not any(map(get_origin, get_args(field_type)))
        and not any(
            not is_type_var(base_arg) and base_arg != field_arg
            for base_arg, field_arg in zip(get_args(base), get_args(field_type))
        )
    ):
        type_vars = {}
        for base_arg, field_arg in zip(get_args(base), get_args(field_type)):
            if base_arg in type_vars and type_vars[base_arg] != field_arg:
                type_vars = None
                break
            type_vars[base_arg] = field_arg
        field_type_origin, base_origin = get_origin(field_type), get_origin(base)
        assert field_type_origin is not None and base_origin is not None
        if base_origin != field_type_origin:
            if covariant and not issubclass(base_origin, field_type_origin):
                type_vars = None
            if contravariant and not issubclass(field_type_origin, base_origin):
                type_vars = None
    return resolve_type_vars(other, type_vars)


def deserializer_parameter(deserializer: Converter, field_type: AnyType) -> AnyType:
    try:
        param, ret = check_converter(deserializer, None, None)
    except TypeError:
        param, _ = check_converter(deserializer, None, field_type)
    else:
        param = handle_generic_field_type(field_type, ret, param, True)
    return param


def serializer_return(serializer: Converter, field_type: AnyType) -> AnyType:
    try:
        param, ret = check_converter(serializer, None, None)
    except TypeError:
        _, ret = check_converter(serializer, field_type, None)
    else:
        ret = handle_generic_field_type(field_type, param, ret, False)
    return ret


Cls = TypeVar("Cls", bound=Type)


@dataclass
class FieldConversions(MetadataMixin):
    deserialization: Optional[Conversions] = None
    serialization: Optional[Conversions] = None
    deserializer: Optional[Converter] = None
    serializer: Optional[Converter] = None

    def __post_init__(self):
        from apischema.metadata.keys import CONVERSIONS_METADATA

        super().__init__(CONVERSIONS_METADATA)

    def __call__(self, dataclass: Cls) -> Cls:
        from apischema.metadata.keys import CONVERSIONS_METADATA, MERGED_METADATA

        if not is_dataclass(dataclass):
            raise TypeError("Must be applied to dataclass")
        for conv in (self.deserialization, self.serialization):
            if conv is not None and not isinstance(conv, Mapping):
                raise TypeError("Dataclasses conversions must be a Mapping instance")
        for field in fields(dataclass):
            if field.metadata.get(MERGED_METADATA):
                continue
            if CONVERSIONS_METADATA in field.metadata:
                conversions: FieldConversions = field.metadata[CONVERSIONS_METADATA]
                if any((self.deserialization, conversions.deserialization)):
                    conversions.deserialization = ChainMap(
                        conversions.deserialization or {}, self.deserialization or {}
                    )
                if any((self.serialization, conversions.serialization)):
                    conversions.serialization = ChainMap(
                        conversions.serialization or {}, self.serialization or {}
                    )
            else:
                conversions = FieldConversions(
                    deserialization=self.deserialization,
                    serialization=self.serialization,
                )
                field.metadata = MappingProxyType({CONVERSIONS_METADATA: conversions})
        return dataclass


@dataclass
class FieldConversionsModel(MetadataMixin):
    model: AnyType

    def __post_init__(self):
        from apischema.metadata.keys import CONVERSIONS_METADATA

        super().__init__(CONVERSIONS_METADATA)


@overload
def conversions(model: AnyType) -> Metadata:
    ...


@overload
def conversions(
    *,
    deserialization: Conversions = None,
    serialization: Conversions = None,
    deserializer: Converter = None,
    serializer: Converter = None,
    raw_deserializer: Callable = None,
) -> FieldConversions:
    ...


def conversions(
    model: AnyType = None,
    *,
    deserialization: Conversions = None,
    serialization: Conversions = None,
    deserializer: Converter = None,
    serializer: Converter = None,
    raw_deserializer: Callable = None,
) -> Metadata:
    if model is not None:
        return FieldConversionsModel(model)
    else:
        if raw_deserializer is not None:
            deserializer = to_raw_deserializer(raw_deserializer)
        return FieldConversions(
            deserialization, serialization, deserializer, serializer
        )
