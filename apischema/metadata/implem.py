import re
from dataclasses import dataclass
from typing import Callable, Optional, Pattern, TYPE_CHECKING, Tuple, Union

from apischema.metadata.keys import (
    CONVERSIONS_METADATA,
    DEFAULT_AS_SET,
    DEFAULT_FALLBACK_METADATA,
    INIT_VAR_METADATA,
    MERGED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SKIP_METADATA,
    VALIDATORS_METADATA,
)
from apischema.types import AnyType, MetadataImplem, Metadata, MetadataMixin

if TYPE_CHECKING:
    from apischema.conversions.conversions import Conversions
    from apischema.validation.validator import Validator


def simple_metadata(key: str) -> Metadata:
    return MetadataImplem({key: ...})


@dataclass(frozen=True)
class ConversionMetadata(MetadataMixin):
    key = CONVERSIONS_METADATA
    deserialization: Optional["Conversions"] = None
    serialization: Optional["Conversions"] = None


if False:  # For Pycharm

    def conversion(
        deserialization: "Conversions" = None,
        serialization: "Conversions" = None,
    ) -> ConversionMetadata:
        ...


else:
    conversion = ConversionMetadata


default_as_set = simple_metadata(DEFAULT_AS_SET)

default_fallback = simple_metadata(DEFAULT_FALLBACK_METADATA)


def init_var(tp: AnyType) -> Metadata:
    return MetadataImplem({INIT_VAR_METADATA: tp})


merged = simple_metadata(MERGED_METADATA)

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

skip = simple_metadata(SKIP_METADATA)


@dataclass(frozen=True)
class ValidatorsMetadata(MetadataMixin):
    key = VALIDATORS_METADATA
    validators: Tuple["Validator", ...]


def validators(*validator: Callable) -> ValidatorsMetadata:
    from apischema.validation.validator import Validator

    return ValidatorsMetadata(tuple(map(Validator, validator)))
