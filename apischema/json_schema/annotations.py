from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Union

from apischema.types import Undefined

Deprecated = Union[bool, str]


@dataclass(frozen=True)
class Annotations:
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = Undefined
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None
    deprecated: Optional[Deprecated] = None

    def merge_into(self, base_schema: Dict[str, Any]):
        if self.deprecated:
            base_schema["deprecated"] = bool(self.deprecated)
        for k in ("title", "description", "examples", "format"):
            if getattr(self, k) is not None:
                base_schema[k] = getattr(self, k)
        if self.default is not Undefined:
            base_schema["default"] = self.default
