from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Optional, Sequence, Union

from apischema.utils import Undefined, merge_opts, merge_opts_mapping

Deprecated = Union[bool, str]


@dataclass(frozen=True)
class Annotations:
    extra: Optional[Mapping[str, Any]] = None
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = Undefined
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None
    deprecated: Deprecated = False

    def as_dict(self) -> Mapping[str, Any]:
        result: Dict[str, Any] = {}
        if self.deprecated:
            result["deprecated"] = self.deprecated
        for k in ("title", "description", "examples", "format"):
            if getattr(self, k) is not None:
                result[k] = getattr(self, k)
        if self.default is not Undefined:
            result["default"] = self.default
        if self.extra:
            result.update(self.extra)
        return result


@merge_opts
def merge_annotations(default: Annotations, override: Annotations) -> Annotations:
    merged_fields = {
        f.name: getattr(override, f.name) or getattr(default, f.name)
        for f in fields(Annotations)
    }
    if override.default is not Undefined:
        merged_fields["default"] = override.default
    else:
        merged_fields["default"] = default.default
    merged_fields["extra"] = merge_opts_mapping(default.extra, override.extra)  # type: ignore # noqa: E501
    return Annotations(**merged_fields)
