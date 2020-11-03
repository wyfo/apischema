from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from apischema.utils import Nil, as_dict, merge_opts, merge_opts_mapping


@dataclass(frozen=True)
class Annotations:
    extra: Optional[Mapping[str, Any]] = None
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = Nil
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None

    def as_dict(self) -> Mapping[str, Any]:
        result = {}
        for k in ("title", "description", "examples", "format"):
            if getattr(self, k) is not None:
                result[k] = getattr(self, k)
        if self.default is not Nil:
            result["default"] = self.default
        if self.extra:
            result.update(self.extra)
        return result


@merge_opts
def merge_annotations(default: Annotations, override: Annotations) -> Annotations:
    return Annotations(
        **{
            **as_dict(default),
            **as_dict(override),
            "extra": merge_opts_mapping(default.extra, override.extra),  # type: ignore
        }
    )
