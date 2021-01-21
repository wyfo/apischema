from dataclasses import dataclass
from typing import (
    Callable,
    Collection,
    Optional,
    TYPE_CHECKING,
    Tuple,
    Union,
)

from apischema.cache import cache
from apischema.conversions.utils import (
    Converter,
    converter_types,
    get_conversion_type,
    identity,
    is_convertible,
)
from apischema.dataclasses import replace
from apischema.types import AnyType
from apischema.utils import cached_property, is_method, method_class, method_wrapper

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coercion


@dataclass(frozen=True)
class Conversion:
    converter: Union[Converter, property]
    source: AnyType = None
    target: AnyType = None
    conversions: Optional["Conversions"] = None
    lazy_conversions: Optional[Callable[[], Optional["Conversions"]]] = None
    additional_properties: Optional[bool] = None
    coercion: Optional["Coercion"] = None
    default_fallback: Optional[bool] = None
    exclude_unset: Optional[bool] = None

    def __call__(self, *args, **kwargs):
        return self.converter(*args, **kwargs)


ConvOrFunc = Union[Conversion, Converter, property]
Conversions = Union[ConvOrFunc, Collection[ConvOrFunc]]
HashableConversions = Union[ConvOrFunc, Tuple[ConvOrFunc, ...]]


@dataclass
class ResolvedConversion:
    converter: Converter
    source: AnyType
    target: AnyType
    get_conversions: Optional[Callable[[], Optional[Conversions]]]
    lazy: bool
    additional_properties: Optional[bool]
    coercion: Optional["Coercion"]
    default_fallback: Optional[bool]
    exclude_unset: Optional[bool]

    @staticmethod
    def from_conversion(conversion: Conversion) -> "ResolvedConversion":
        assert not isinstance(conversion.converter, property)
        assert conversion.source is not None and conversion.target is not None
        get_conversions: Optional[Callable[[], Optional[Conversions]]]
        lazy = False
        if conversion.conversions is not None:
            get_conversions = lambda: conversion.conversions  # noqa: E731
        elif conversion.lazy_conversions is not None:
            get_conversions = conversion.lazy_conversions
            lazy = True
        else:
            get_conversions = None
        return ResolvedConversion(
            conversion.converter,
            conversion.source,
            conversion.target,
            get_conversions,
            lazy,
            conversion.additional_properties,
            conversion.coercion,
            conversion.default_fallback,
            conversion.exclude_unset,
        )

    @cached_property
    def conversions(self) -> Optional["HashableConversions"]:
        if self.get_conversions is not None:
            return to_hashable_conversions(self.get_conversions())
        else:
            return None

    @property
    def is_identity(self) -> bool:
        return (
            self.converter == identity
            and self.source == self.target
            and all(
                attr is None
                for attr in (
                    self.get_conversions,
                    self.additional_properties,
                    self.coercion,
                    self.default_fallback,
                    self.exclude_unset,
                )
            )
        )


# ResolvedConversion = NewType("ResolvedConversion", Conversion)

ConversionResolver = Callable[[ConvOrFunc], ResolvedConversion]


def to_hashable_conversions(
    conversions: Optional[Conversions],
) -> Optional[HashableConversions]:
    if conversions is None:
        return None
    elif isinstance(conversions, Collection):
        return tuple(conversions)
    else:
        return conversions


def resolve_conversions(
    conversions: Conversions, resolver: ConversionResolver
) -> Collection[ResolvedConversion]:
    if not isinstance(conversions, Collection):
        conversions = [conversions]
    return tuple(map(resolver, conversions))


@cache
def resolve_deserialization(conversion: ConvOrFunc) -> ResolvedConversion:
    if not isinstance(conversion, Conversion):
        conversion = Conversion(conversion)
    if isinstance(conversion.converter, property):
        raise TypeError("Properties cannot be used for deserialization conversions")
    source, target = converter_types(
        conversion.converter, conversion.source, conversion.target
    )
    target, source = get_conversion_type(target, source)
    if not is_convertible(target):
        raise TypeError(f"Target of {conversion} is not a convertible class")
    return ResolvedConversion.from_conversion(
        replace(conversion, source=source, target=target)
    )


def handle_serialization_method(conversion: Conversion) -> Conversion:
    if is_method(conversion.converter):
        if conversion.source is None:
            conversion = replace(conversion, source=method_class(conversion.converter))
        return replace(conversion, converter=method_wrapper(conversion.converter))
    else:
        return conversion


@cache
def resolve_serialization(conversion: ConvOrFunc) -> ResolvedConversion:
    if not isinstance(conversion, Conversion):
        conversion = Conversion(conversion)
    conversion = handle_serialization_method(conversion)
    assert not isinstance(conversion.converter, property)
    source, target = converter_types(
        conversion.converter, conversion.source, conversion.target
    )
    source, target = get_conversion_type(source, target)
    if not is_convertible(source):
        raise TypeError(f"Source of {conversion} is not a convertible class")
    return ResolvedConversion.from_conversion(
        replace(conversion, source=source, target=target)
    )
