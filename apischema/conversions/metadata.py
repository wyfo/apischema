from collections import ChainMap
from dataclasses import Field, dataclass, fields
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Type, TypeVar, overload

from apischema.conversions.raw import to_raw_deserializer
from apischema.conversions.utils import (
    Conversions,
    Converter,
    check_converter,
    substitute_type_vars,
    type_var_remap,
)
from apischema.conversions.visitor import Deserialization, Serialization
from apischema.dataclass_utils import is_dataclass
from apischema.types import AnyType, Metadata, MetadataMixin

Cls = TypeVar("Cls", bound=Type)


@dataclass
class ConversionsMetadata(MetadataMixin):
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
                conversions: ConversionsMetadata = field.metadata[CONVERSIONS_METADATA]
                if any((self.deserialization, conversions.deserialization)):
                    conversions.deserialization = ChainMap(
                        conversions.deserialization or {}, self.deserialization or {}
                    )
                if any((self.serialization, conversions.serialization)):
                    conversions.serialization = ChainMap(
                        conversions.serialization or {}, self.serialization or {}
                    )
            else:
                conversions = ConversionsMetadata(
                    deserialization=self.deserialization,
                    serialization=self.serialization,
                )
                field.metadata = MappingProxyType({CONVERSIONS_METADATA: conversions})
        return dataclass

    def deserialization_conversion(self, field_type: AnyType) -> Deserialization:
        assert self.deserializer is not None
        try:
            param, ret = check_converter(self.deserializer, None, None)
        except TypeError:
            param, _ = check_converter(self.deserializer, None, field_type)
        else:
            param = substitute_type_vars(param, dict(type_var_remap(field_type, ret)))
        return {param: (self.deserializer, self.deserialization)}

    def serialization_conversion(self, field_type: AnyType) -> Serialization:
        assert self.serializer is not None
        try:
            param, ret = check_converter(self.serializer, None, None)
        except TypeError:
            param, _ = check_converter(self.serializer, field_type, None)
        else:
            param = substitute_type_vars(ret, dict(type_var_remap(field_type, param)))
        return param, (self.serializer, self.serialization)


@dataclass
class ConversionsMetadataFactory(MetadataMixin):
    factory: Callable[[AnyType], ConversionsMetadata]

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
) -> ConversionsMetadata:
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
        return ConversionsMetadataFactory(
            lambda cls: ConversionsMetadata({cls: model}, {cls: model})
        )
    else:
        if raw_deserializer is not None:
            deserializer = to_raw_deserializer(raw_deserializer)
        return ConversionsMetadata(
            deserialization, serialization, deserializer, serializer
        )


def get_field_conversions(
    field: Field, field_type: AnyType
) -> Optional[ConversionsMetadata]:
    from apischema.metadata.keys import CONVERSIONS_METADATA

    if CONVERSIONS_METADATA not in field.metadata:
        return None
    else:
        conversions = field.metadata[CONVERSIONS_METADATA]
        if isinstance(conversions, ConversionsMetadataFactory):
            conversions = conversions.factory(field_type)  # type: ignore
        return conversions
