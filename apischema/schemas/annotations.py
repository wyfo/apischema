from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Union

from apischema.utils import to_camel_case

Deprecated = Union[bool, str]
try:
    from apischema.typing import Literal

    ContentEncoding = Literal["7bit", "8bit", "binary", "quoted-printable", "base64"]
except ImportError:
    ContentEncoding = str  # type: ignore


@dataclass(frozen=True)
class Annotations:
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Callable[[], Any]] = None
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None
    deprecated: Optional[Deprecated] = None
    media_type: Optional[str] = None
    encoding: Optional[ContentEncoding] = None

    def merge_into(self, base_schema: Dict[str, Any]):
        if self.deprecated:
            base_schema["deprecated"] = bool(self.deprecated)
        for k in ("title", "description", "examples", "format"):
            if getattr(self, k) is not None:
                base_schema[k] = getattr(self, k)
        for k in ("media_type", "encoding"):
            if getattr(self, k) is not None:
                base_schema[to_camel_case("content_" + k)] = getattr(self, k)
        if self.default is not None:
            base_schema["default"] = self.default()
