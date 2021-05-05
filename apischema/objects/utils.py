from typing import Mapping

from apischema.metadata.implem import ValidatorsMetadata
from apischema.metadata.keys import SCHEMA_METADATA, VALIDATORS_METADATA
from apischema.types import AnyType, ChainMap
from apischema.typing import get_args, is_annotated
from apischema.utils import empty_dict


class AliasedStr(str):
    pass


# These metadata are not specific to fields and mostly handled in Visitor.annotated
ANNOTATED_METADATA = {
    SCHEMA_METADATA: None,
    VALIDATORS_METADATA: ValidatorsMetadata(()),
}


def annotated_metadata(tp: AnyType) -> Mapping:
    if is_annotated(tp):
        return ChainMap(
            ANNOTATED_METADATA,
            *(arg for arg in reversed(get_args(tp)[1:]) if isinstance(arg, Mapping)),
        )
    else:
        return empty_dict
