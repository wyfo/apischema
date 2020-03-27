from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Union

from apischema.utils import NO_DEFAULT, PREFIX

ANNOTATIONS_METADATA = f"{PREFIX}description"


@dataclass
class Annotations:
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = NO_DEFAULT
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None
    items: Optional[Union["Annotations", Sequence["Annotations"]]] = None
    additional_properties: Optional["Annotations"] = None


_annotations: Dict[Any, Annotations] = {}

get_annotations = _annotations.get
