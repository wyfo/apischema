from dataclasses import Field
from typing import Mapping

from apischema.types import AnyType, ChainMap
from apischema.typing import get_args, get_origin
from apischema.utils import PREFIX

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

ALIAS_METADATA = f"{PREFIX}alias"
ALIAS_NO_OVERRIDE_METADATA = f"{PREFIX}alias_no_override"
CONVERSION_METADATA = f"{PREFIX}conversion"
DEFAULT_AS_SET_METADATA = f"{PREFIX}default_as_set"
DEFAULT_FALLBACK_METADATA = f"{PREFIX}default_fallback"
INIT_VAR_METADATA = f"{PREFIX}init_var"
MERGED_METADATA = f"{PREFIX}merged"
POST_INIT_METADATA = f"{PREFIX}post_init"
PROPERTIES_METADATA = f"{PREFIX}properties"
REQUIRED_METADATA = f"{PREFIX}required"
SCHEMA_METADATA = f"{PREFIX}schema"
SKIP_METADATA = f"{PREFIX}skip"
VALIDATORS_METADATA = f"{PREFIX}validators"

FORBIDDEN_WITH_AGGREGATE = {
    ALIAS_METADATA,
    ALIAS_NO_OVERRIDE_METADATA,
    DEFAULT_AS_SET_METADATA,
    POST_INIT_METADATA,
    REQUIRED_METADATA,
    SCHEMA_METADATA,
    VALIDATORS_METADATA,
}


def is_aggregate_field(field: Field) -> bool:
    return MERGED_METADATA in field.metadata or PROPERTIES_METADATA in field.metadata


def get_annotated_metadata(tp: AnyType) -> Mapping:
    if get_origin(tp) == Annotated:
        return ChainMap(*(arg for arg in get_args(tp)[1:] if isinstance(arg, Mapping)))
    else:
        return {}
