import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Pattern, TYPE_CHECKING, Tuple, Union

from apischema.metadata.keys import (
    CONVERSION_METADATA,
    DEFAULT_AS_SET_METADATA,
    FALL_BACK_ON_DEFAULT_METADATA,
    FLATTEN_METADATA,
    INIT_VAR_METADATA,
    NONE_AS_UNDEFINED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SKIP_METADATA,
    VALIDATORS_METADATA,
)
from apischema.types import AnyType, Metadata, MetadataImplem, MetadataMixin

if TYPE_CHECKING:
    from apischema.conversions.conversions import AnyConversion
    from apischema.validation.validators import Validator


def simple_metadata(key: str) -> Metadata:
    return MetadataImplem({key: ...})


@dataclass(frozen=True)
class ConversionMetadata(MetadataMixin):
    key = CONVERSION_METADATA
    deserialization: Optional["AnyConversion"] = None
    serialization: Optional["AnyConversion"] = None


conversion = ConversionMetadata

default_as_set = simple_metadata(DEFAULT_AS_SET_METADATA)

fall_back_on_default = simple_metadata(FALL_BACK_ON_DEFAULT_METADATA)

flatten = simple_metadata(FLATTEN_METADATA)
flattened = flatten
merged = flatten


def init_var(tp: AnyType) -> Metadata:
    return MetadataImplem({INIT_VAR_METADATA: tp})


none_as_undefined = simple_metadata(NONE_AS_UNDEFINED_METADATA)

post_init = simple_metadata(POST_INIT_METADATA)


class PropertiesMetadata(dict, Metadata):  # type: ignore
    def __init__(self):
        super().__init__({PROPERTIES_METADATA: None})

    def __call__(
        self, pattern: Union[str, Pattern, "ellipsis"]  # noqa: F821
    ) -> Metadata:
        if pattern is not ...:
            pattern = re.compile(pattern)
        return MetadataImplem({PROPERTIES_METADATA: pattern})


properties = PropertiesMetadata()

required = simple_metadata(REQUIRED_METADATA)


@dataclass(frozen=True)
class SkipMetadata(MetadataMixin):
    key = SKIP_METADATA
    deserialization: bool = False
    serialization: bool = False
    serialization_default: bool = False
    serialization_if: Optional[Callable[[Any], Any]] = None

    def __call__(
        self,
        deserialization: bool = False,
        serialization: bool = False,
        serialization_default: bool = False,
        serialization_if: Optional[Callable[[Any], Any]] = None,
    ) -> "SkipMetadata":
        return SkipMetadata(
            deserialization, serialization, serialization_default, serialization_if
        )


skip = SkipMetadata(deserialization=True, serialization=True)


@dataclass(frozen=True)
class ValidatorsMetadata(MetadataMixin):
    key = VALIDATORS_METADATA
    validators: Tuple["Validator", ...]


def validators(*validator: Callable) -> ValidatorsMetadata:
    from apischema.validation.validators import Validator

    return ValidatorsMetadata(tuple(map(Validator, validator)))
