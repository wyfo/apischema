import re
from typing import Optional, Pattern, Union

from apischema.types import DictWithUnion, Metadata
from apischema.utils import PREFIX

PROPERTIES_METADATA = f"{PREFIX}properties"


def properties(pattern: Optional[Union[str, Pattern]] = None) -> Metadata:
    if pattern is not None:
        pattern = re.compile(pattern)
    return DictWithUnion({PROPERTIES_METADATA: pattern})
