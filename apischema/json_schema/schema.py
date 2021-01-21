from contextlib import suppress
from dataclasses import dataclass, fields
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    TypeVar,
    Union,
    overload,
)

from apischema.types import AnyType, MetadataMixin, Number
from apischema.utils import Undefined, merge_opts
from .annotations import Annotations, Deprecated, merge_annotations
from .constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
    merge_constraints,
)
from .types import replace_builtins
from ..metadata.keys import SCHEMA_METADATA

T = TypeVar("T")


@dataclass(frozen=True)
class Schema(MetadataMixin):
    key = SCHEMA_METADATA
    annotations: Optional[Annotations] = None
    constraints: Optional[Constraints] = None
    override: bool = False

    def __call__(self, obj: T) -> T:
        _schema[replace_builtins(obj)] = self
        return obj

    def __set_name__(self, owner, name):
        self.__call__(owner)

    def as_dict(self) -> Mapping[str, Any]:
        result: Dict[str, Any] = {}
        if self.constraints is not None:
            result.update(self.constraints.as_dict())
        if self.annotations is not None:
            result.update(self.annotations.as_dict())
        return result


_annotations_fields = {f.name for f in fields(Annotations)}


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: Deprecated = False,
    extra: Mapping[str, Any] = None,
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
    deprecated: Deprecated = False,
    min: Optional[Number] = None,
    max: Optional[Number] = None,
    exc_min: Optional[Number] = None,
    exc_max: Optional[Number] = None,
    mult_of: Optional[Number] = None,
    extra: Mapping[str, Any] = None,
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
    deprecated: Deprecated = False,
    format: Optional[str] = None,
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    pattern: Optional[Union[str, Pattern]] = None,
    extra: Mapping[str, Any] = None,
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
    deprecated: Deprecated = False,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique: Optional[bool] = None,
    extra: Mapping[str, Any] = None,
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
    deprecated: Deprecated = False,
    min_props: Optional[int] = None,
    max_props: Optional[int] = None,
    extra: Mapping[str, Any] = None,
    override: bool = False,
) -> Schema:
    ...


def schema(override=False, **kwargs) -> Schema:
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
            raise TypeError("Invalid schema")

    return Schema(annotations, constraints, override)


def _default_schema(cls: AnyType) -> Optional[Schema]:
    return None


_schema: Dict[Any, Schema] = {}


def get_schema(cls: AnyType) -> Optional[Schema]:
    cls = replace_builtins(cls)
    return _schema[cls] if cls in _schema else _default_schema(cls)


@merge_opts
def merge_schema(default: Schema, override: Schema) -> Schema:
    if override.override:
        return override
    return Schema(
        merge_annotations(default.annotations, override.annotations),
        merge_constraints(default.constraints, override.constraints),
        override.override,
    )
