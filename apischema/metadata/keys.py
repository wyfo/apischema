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
CONVERSIONS_METADATA = f"{PREFIX}conversions"
DEFAULT_AS_SET = f"{PREFIX}default_as_set"
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
    DEFAULT_AS_SET,
    POST_INIT_METADATA,
    REQUIRED_METADATA,
    SCHEMA_METADATA,
    VALIDATORS_METADATA,
}


def is_aggregate_field(field: Field) -> bool:
    return MERGED_METADATA in field.metadata or PROPERTIES_METADATA in field.metadata


def check_metadata(field: Field) -> Mapping:
    if MERGED_METADATA in field.metadata and PROPERTIES_METADATA in field.metadata:
        raise TypeError("merged and properties metadata are incompatible")
    if is_aggregate_field(field):
        forbidden = FORBIDDEN_WITH_AGGREGATE & field.metadata.keys()
        if forbidden:
            raise TypeError(f"{forbidden} metadata are not allowed in aggregate field")
    return field.metadata


def get_annotated_metadata(tp: AnyType) -> Mapping:
    if get_origin(tp) == Annotated:
        return ChainMap(*(arg for arg in get_args(tp)[1:] if isinstance(arg, Mapping)))
    else:
        return {}
