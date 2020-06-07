from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from apischema.utils import Nil


@dataclass(frozen=True)
class Annotations:
    extra: Optional[Mapping[str, Any]] = None
    extra_only: bool = False
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = Nil
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None


_annotations: Dict[Any, Annotations] = {}

get_annotations = _annotations.get

NO_DEFAULT = object()
