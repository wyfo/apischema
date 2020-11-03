from contextlib import suppress
from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Optional, Sequence, TypeVar, overload

from apischema.types import AnyType, MetadataMixin, Number
from apischema.utils import Nil, merge_opts
from .annotations import Annotations, merge_annotations
from .constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
    merge_constraints,
)

T = TypeVar("T")


@dataclass(frozen=True)
class Schema(MetadataMixin):
    annotations: Optional[Annotations] = None
    constraints: Optional[Constraints] = None
    override: bool = False

    def __post_init__(self):
        from apischema.metadata.keys import SCHEMA_METADATA

        super().__init__(SCHEMA_METADATA)

    def __call__(self, obj: T) -> T:
        _schema[obj] = self
        return obj

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
    default: Any = Nil,
    examples: Optional[Sequence[Any]] = None,
    extra: Mapping[str, Any] = None,
    override: bool = False,
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Nil,
    examples: Optional[Sequence[Any]] = None,
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
    default: Any = Nil,
    examples: Optional[Sequence[Any]] = None,
    format: Optional[str] = None,
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    pattern: Optional[str] = None,
    extra: Mapping[str, Any] = None,
    override: bool = False,
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Nil,
    examples: Optional[Sequence[Any]] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique: Optional[bool] = None,
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
    return _schema[cls] if cls in _schema else _default_schema(cls)


@merge_opts
def merge_schema(default: Schema, override: Schema) -> Schema:
    # override will be the higher level schema, so schema generation
    # should not go further and merge not happen
    assert not override.override
    return Schema(
        merge_annotations(default.annotations, override.annotations),
        merge_constraints(default.constraints, override.constraints),
        override.override,
    )
