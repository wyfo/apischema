from collections import ChainMap
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import (
    Callable,
    Mapping,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from apischema.conversion.raw import to_raw_deserializer
from apischema.conversion.utils import Conversions, Converter
from apischema.dataclasses import is_dataclass
from apischema.types import AnyType, MetadataMixin

Cls = TypeVar("Cls", bound=Type)


@dataclass
class ConversionsMetadata(MetadataMixin):
    both: Optional[AnyType] = None
    deserialization: Optional[Conversions] = None
    serialization: Optional[Conversions] = None
    deserializer: Optional[Converter] = None
    serializer: Optional[Converter] = None

    def __post_init__(self):
        from apischema.metadata.keys import CONVERSIONS_METADATA

        super().__init__(CONVERSIONS_METADATA)
        if (
            self.both is not None
            and len([f for f in fields(self) if getattr(self, f.name) is not None]) > 1
        ):
            raise ValueError("Cannot set both and (de)serialization/(de)serializers")

    def __call__(self, dataclass: Cls) -> Cls:
        from apischema.metadata.keys import CONVERSIONS_METADATA, MERGED_METADATA

        if not is_dataclass(dataclass):
            raise TypeError("Must be applied to dataclass")
        for conv in (self.deserialization, self.serialization):
            if conv is not None and not isinstance(conv, Mapping):
                raise TypeError("Dataclasses conversions must be a Mapping instance")
        for field in fields(dataclass):
            if MERGED_METADATA in field.metadata:
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


Conversions_ = Union[Mapping[AnyType, AnyType], AnyType]


@overload
def conversions(both: AnyType = None) -> ConversionsMetadata:
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
    both: AnyType = None,
    *,
    deserialization: Conversions = None,
    serialization: Conversions = None,
    deserializer: Converter = None,
    serializer: Converter = None,
    raw_deserializer: Callable = None,
) -> ConversionsMetadata:
    if raw_deserializer is not None:
        deserializer = to_raw_deserializer(raw_deserializer)
    return ConversionsMetadata(
        both, deserialization, serialization, deserializer, serializer
    )
