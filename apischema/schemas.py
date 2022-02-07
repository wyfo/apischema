import re
from dataclasses import dataclass, replace
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    TypeVar,
    Union,
)

from apischema.constraints import Constraints
from apischema.metadata.keys import SCHEMA_METADATA
from apischema.types import AnyType, MetadataMixin, Number, Undefined
from apischema.typing import is_annotated
from apischema.utils import merge_opts, replace_builtins, to_camel_case

T = TypeVar("T")
Extra = Union[Mapping[str, Any], Callable[[Dict[str, Any]], None]]

Deprecated = Union[bool, str]
try:
    from apischema.typing import Literal

    ContentEncoding = Literal["7bit", "8bit", "binary", "quoted-printable", "base64"]
except ImportError:
    ContentEncoding = str  # type: ignore


@dataclass(frozen=True)
class Schema(MetadataMixin):
    key = SCHEMA_METADATA
    title: Optional[str] = None
    description: Optional[str] = None
    # use a callable wrapper in order to be hashable
    default: Optional[Callable[[], Any]] = None
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None
    deprecated: Optional[Deprecated] = None
    media_type: Optional[str] = None
    encoding: Optional[ContentEncoding] = None
    constraints: Optional[Constraints] = None
    extra: Optional[Callable[[Dict[str, Any]], None]] = None
    override: bool = False
    child: Optional["Schema"] = None

    def __call__(self, tp: T) -> T:
        if is_annotated(tp):
            raise TypeError("Cannot register schema on Annotated type")
        _schemas[replace_builtins(tp)] = self
        return tp

    def merge_into(self, base_schema: Dict[str, Any]):
        if self.override:
            base_schema.clear()
        elif self.child is not None:
            self.child.merge_into(base_schema)
        if self.constraints is not None:
            self.constraints.merge_into(base_schema)
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
        if self.extra is not None:
            self.extra(base_schema)


def schema(
    *,
    # annotations
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: Optional[Deprecated] = None,
    # number
    min: Optional[Number] = None,
    max: Optional[Number] = None,
    exc_min: Optional[Number] = None,
    exc_max: Optional[Number] = None,
    mult_of: Optional[Number] = None,
    # string
    format: Optional[str] = None,
    media_type: Optional[str] = None,
    encoding: Optional[ContentEncoding] = None,
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    pattern: Optional[Union[str, Pattern]] = None,
    # array
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique: Optional[bool] = None,
    # objects
    min_props: Optional[int] = None,
    max_props: Optional[int] = None,
    # extra
    extra: Optional[Extra] = None,
    override: bool = False,
) -> Schema:
    default = None if default is Undefined else (lambda d=default: d)
    if pattern is not None:
        pattern = re.compile(pattern)
    if isinstance(extra, Mapping):
        extra = lambda js, to_update=extra: js.update(to_update)  # type: ignore
    constraints = Constraints(
        min=min,
        max=max,
        exc_min=exc_min,
        exc_max=exc_max,
        mult_of=mult_of,
        min_len=min_len,
        max_len=max_len,
        pattern=pattern,
        min_items=min_items,
        max_items=max_items,
        unique=unique,
        min_props=min_props,
        max_props=max_props,
    )
    return Schema(
        title=title,
        description=description,
        default=default,
        examples=examples,
        format=format,
        deprecated=deprecated,
        media_type=media_type,
        encoding=encoding,
        constraints=constraints,
        extra=extra,
        override=override,
    )


_schemas: Dict[Any, Schema] = {}


def get_schema(tp: AnyType) -> Optional[Schema]:
    tp = replace_builtins(tp)
    try:
        return _schemas.get(tp)
    except TypeError:
        return None


@merge_opts
def merge_schema(default: Schema, override: Schema) -> Schema:
    if override.override:
        return override
    return replace(override, child=merge_schema(default, override.child))
