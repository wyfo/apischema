from contextlib import suppress
from dataclasses import dataclass, fields, replace
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
    overload,
)

from apischema.metadata.keys import SCHEMA_METADATA
from apischema.types import AnyType, MetadataMixin, Number, Undefined
from apischema.typing import get_origin
from apischema.utils import contains, merge_opts, replace_builtins, stop_signature_abuse
from .annotations import Annotations, ContentEncoding, Deprecated
from .constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
)

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

T = TypeVar("T")

Extra = Union[Mapping[str, Any], Callable[[Dict[str, Any]], None]]


@dataclass(frozen=True)
class Schema(MetadataMixin):
    key = SCHEMA_METADATA
    annotations: Optional[Annotations] = None
    constraints: Optional[Constraints] = None
    extra: Optional[Extra] = None
    override: bool = False
    child: Optional["Schema"] = None

    def __call__(self, tp: T) -> T:
        if get_origin(tp) is Annotated:
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
        if callable(self.extra):
            self.extra(base_schema)
        elif self.extra is not None:
            base_schema.update(self.extra)  # type: ignore

    def validate(self, data: T) -> T:
        if self.constraints is not None:
            return self.constraints.validate(data)
        else:
            return data


_annotations_fields = {f.name for f in fields(Annotations)}


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: Optional[Deprecated] = None,
    extra: Optional[Extra] = None,
    override: bool = False,
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: Optional[Deprecated] = None,
    min: Optional[Number] = None,
    max: Optional[Number] = None,
    exc_min: Optional[Number] = None,
    exc_max: Optional[Number] = None,
    mult_of: Optional[Number] = None,
    extra: Optional[Extra] = None,
    override: bool = False,
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: Optional[Deprecated] = None,
    format: Optional[str] = None,
    media_type: Optional[str] = None,
    encoding: Optional[ContentEncoding] = None,
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    pattern: Optional[Union[str, Pattern]] = None,
    extra: Optional[Extra] = None,
    override: bool = False,
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: Optional[Deprecated] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique: Optional[bool] = None,
    extra: Optional[Extra] = None,
    override: bool = False,
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: Optional[Deprecated] = None,
    min_props: Optional[int] = None,
    max_props: Optional[int] = None,
    extra: Optional[Extra] = None,
    override: bool = False,
) -> Schema:
    ...


def schema(extra: Extra = None, override=False, **kwargs) -> Schema:
    annotations_kwargs = {k: v for k, v in kwargs.items() if k in _annotations_fields}
    constraints_kwargs = {
        k: v for k, v in kwargs.items() if k not in _annotations_fields
    }
    annotations = Annotations(**annotations_kwargs) if annotations_kwargs else None

    constraints = None
    if constraints_kwargs:
        for cls in (
            NumberConstraints,
            StringConstraints,
            ArrayConstraints,
            ObjectConstraints,
        ):
            with suppress(TypeError):
                constraints = cls(**constraints_kwargs)
                break
        else:
            stop_signature_abuse()

    return Schema(annotations, constraints, extra, override)


def _default_schema(tp: AnyType) -> Optional[Schema]:
    return None


_schemas: Dict[Any, Schema] = {}


def get_schema(tp: AnyType) -> Optional[Schema]:
    tp = replace_builtins(tp)
    return _schemas[tp] if contains(_schemas, tp) else _default_schema(tp)


@merge_opts
def merge_schema(default: Schema, override: Schema) -> Schema:
    if override.override:
        return override
    return replace(override, child=merge_schema(default, override.child))
