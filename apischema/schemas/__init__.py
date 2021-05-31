import re
import warnings
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

from apischema.metadata.keys import SCHEMA_METADATA
from apischema.schemas.annotations import Annotations, ContentEncoding, Deprecated
from apischema.schemas.constraints import Constraints
from apischema.types import AnyType, MetadataMixin, Number, Undefined
from apischema.typing import is_annotated
from apischema.utils import merge_opts, replace_builtins

T = TypeVar("T")
Extra = Union[Mapping[str, Any], Callable[[Dict[str, Any]], None]]


@dataclass(frozen=True)
class Schema(MetadataMixin):
    key = SCHEMA_METADATA
    annotations: Optional[Annotations] = None
    constraints: Optional[Constraints] = None
    extra: Optional[Callable[[Dict[str, Any]], None]] = None
    override: bool = False
    child: Optional["Schema"] = None

    def __call__(self, tp: T) -> T:
        if is_annotated(tp):
            raise TypeError("Cannot register schema on Annotated type")
        _schemas[replace_builtins(tp)] = self
        return tp

    def __set_name__(self, owner, name):
        self.__call__(owner)

    def merge_into(self, base_schema: Dict[str, Any]):
        if self.override:
            base_schema.clear()
        elif self.child is not None:
            self.child.merge_into(base_schema)
        if self.constraints is not None:
            self.constraints.merge_into(base_schema)
        if self.annotations is not None:
            self.annotations.merge_into(base_schema)
        if self.extra is not None:
            self.extra(base_schema)  # type: ignore


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
    if default is ...:
        warnings.warn(
            "default=... is deprecated as default value is now"
            " automatically added to the schema",
            DeprecationWarning,
        )
        default = Undefined
    default = None if default is Undefined else (lambda d=default: d)
    if pattern is not None:
        pattern = re.compile(pattern)
    if isinstance(extra, Mapping):
        extra = lambda js, to_update=extra: js.update(to_update)  # type: ignore
    annotations = Annotations(
        title, description, default, examples, format, deprecated, media_type, encoding
    )
    constraints = Constraints(
        min,
        max,
        exc_min,
        exc_max,
        mult_of,
        min_len,
        max_len,
        pattern,
        min_items,
        max_items,
        unique,
        min_props,
        max_props,
    )
    return Schema(annotations, constraints, extra, override)


def default_schema(tp: AnyType) -> Optional[Schema]:
    return None


_schemas: Dict[Any, Schema] = {}


def get_schema(tp: AnyType) -> Optional[Schema]:
    from apischema import settings

    tp = replace_builtins(tp)
    try:
        return _schemas[tp]
    except (KeyError, TypeError):
        return settings.default_schema(tp)


@merge_opts
def merge_schema(default: Schema, override: Schema) -> Schema:
    if override.override:
        return override
    return replace(override, child=merge_schema(default, override.child))
