from contextlib import suppress
from dataclasses import dataclass, fields
from typing import Any, Mapping, Optional, Sequence, TypeVar, overload

from apischema.types import AnyType, MetadataMixin, Number
from apischema.utils import Nil, as_dict, merge_opts, merge_opts_mapping, to_camel_case
from .annotations import (
    Annotations,
    _annotations,
    get_annotations,
)
from .constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
    _constraints,
    get_constraints,
)

T = TypeVar("T")


@dataclass(frozen=True)
class Schema(MetadataMixin):
    annotations: Optional[Annotations] = None
    constraints: Optional[Constraints] = None

    def __post_init__(self):
        from apischema.metadata.keys import SCHEMA_METADATA

        super().__init__(SCHEMA_METADATA)

    def __call__(self, obj: T) -> T:
        if self.annotations is not None:
            _annotations[obj] = self.annotations
        if self.constraints is not None:
            _constraints[obj] = self.constraints
        return obj

    @property
    def override(self) -> bool:
        return self.annotations is not None and self.annotations.extra_only


_constraint_rewrite = {
    "min": "minimum",
    "max": "maximum",
    "exc_min": "exclusive_minimum",
    "exc_max": "exclusive_maximum",
    "mult_of": "multiple_of",
    "min_len": "min_length",
    "max_len": "max_length",
    "unique": "unique_items",
    "min_props": "min_properties",
    "max_props": "max_properties",
}


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Nil,
    examples: Optional[Sequence[Any]] = None,
    extra: Mapping[str, Any] = None,
    extra_only: bool = False,
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
    extra_only: bool = False,
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
    extra_only: bool = False,
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
    extra_only: bool = False,
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Nil,
    examples: Optional[Sequence[Any]] = None,
    min_props: Optional[int] = None,
    max_props: Optional[int] = None,
    extra: Mapping[str, Any] = None,
    extra_only: bool = False,
) -> Schema:
    ...


def schema(**kwargs) -> Schema:
    kwargs_ = {_constraint_rewrite.get(k, k): v for k, v in kwargs.items()}
    annotations_fields = {f.name for f in fields(Annotations)}
    annotations_kwargs = {k: v for k, v in kwargs_.items() if k in annotations_fields}
    constraint_kwargs = {
        k: v for k, v in kwargs_.items() if k not in annotations_kwargs
    }
    annotations = None
    if annotations_kwargs:
        annotations = Annotations(**annotations_kwargs)

    constraints = None
    if constraint_kwargs:
        for cls in (
            NumberConstraints,
            StringConstraints,
            ArrayConstraints,
            ObjectConstraints,
        ):
            with suppress(TypeError):
                constraints = cls(**constraint_kwargs)
                break
        else:
            raise TypeError("Invalid constraints")

    return Schema(annotations, constraints)


def get_schema(cls: AnyType) -> Schema:
    return Schema(get_annotations(cls), get_constraints(cls))


@merge_opts
def merge_annotations(default: Annotations, override: Annotations) -> Annotations:
    return Annotations(
        **{
            **as_dict(default),
            **as_dict(override),
            "extra": merge_opts_mapping(default.extra, override.extra),  # type: ignore
            "extra_only": default.extra_only or override.extra_only,
        }
    )


@merge_opts
def merge_constraints(default: Constraints, override: Constraints) -> Constraints:
    return default.merge(override)


@merge_opts
def merge_schema(default: Schema, override: Schema) -> Schema:
    return Schema(
        merge_annotations(default.annotations, override.annotations),
        merge_constraints(default.constraints, override.constraints),
    )


def _camel_case_and_remove_none(obj: Any) -> Mapping[str, Any]:
    if obj is None:
        return {}
    return {to_camel_case(k): v for k, v in as_dict(obj).items() if v is not None}


def serialize_schema(schema: Schema) -> Mapping[str, Any]:
    result = {
        **_camel_case_and_remove_none(schema.annotations),
        **_camel_case_and_remove_none(schema.constraints),
    }
    if schema.annotations is not None:
        if schema.annotations.default is Nil:
            result.pop("default")
        elif schema.annotations.default is None:
            result["default"] = None
    result.pop("extraOnly", ...)
    result.update(result.pop("extra", {}))
    return result
