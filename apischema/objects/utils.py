from typing import Any, Mapping


from apischema.metadata.implem import ValidatorsMetadata
from apischema.metadata.keys import SCHEMA_METADATA, VALIDATORS_METADATA
from apischema.types import AnyType, ChainMap
from apischema.typing import get_args, get_origin

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore


class AliasedStr(str):
    pass


empty_dict: Mapping[str, Any] = {}

# These metadata are not specific to fields and mostly handled in Visitor.annotated
ANNOTATED_METADATA = {
    SCHEMA_METADATA: None,
    VALIDATORS_METADATA: ValidatorsMetadata(()),
}


def annotated_metadata(tp: AnyType) -> Mapping:
    if get_origin(tp) == Annotated:
        return ChainMap(
            ANNOTATED_METADATA,
            *(arg for arg in reversed(get_args(tp)[1:]) if isinstance(arg, Mapping)),
        )
    else:
        return empty_dict
