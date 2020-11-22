import re
from typing import Pattern, Union

from apischema.metadata.keys import (
    DEFAULT_AS_SET,
    DEFAULT_FALLBACK_METADATA,
    INIT_VAR_METADATA,
    MERGED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SKIP_METADATA,
)
from apischema.types import AnyType, MappingWithUnion, Metadata


def simple_metadata(key: str) -> Metadata:
    return MappingWithUnion({key: ...})


default_as_set = simple_metadata(DEFAULT_AS_SET)

default_fallback = simple_metadata(DEFAULT_FALLBACK_METADATA)


def init_var(cls: AnyType) -> Metadata:
    return MappingWithUnion({INIT_VAR_METADATA: cls})


merged = simple_metadata(MERGED_METADATA)

post_init = simple_metadata(POST_INIT_METADATA)


class PropertiesMetadata(dict, Metadata):
    def __init__(self):
        super().__init__({PROPERTIES_METADATA: None})

    def __call__(
        self, pattern: Union[str, Pattern, "ellipsis"]  # noqa: F821
    ) -> Metadata:
        if pattern is not ...:
            pattern = re.compile(pattern)
        return MappingWithUnion({PROPERTIES_METADATA: pattern})


properties = PropertiesMetadata()


required = simple_metadata(REQUIRED_METADATA)

skip = simple_metadata(SKIP_METADATA)
