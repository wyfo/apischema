__all__ = ["get_schema", "schema", "Schema", "Annotations", "Constraint"]

from dataclasses import dataclass, fields
from typing import Any, Dict, Optional, Sequence, Type, TypeVar, Union, overload

from apischema.types import MetadataMixin, Number
from .annotations import (
    ANNOTATIONS_METADATA,
    Annotations,
    _annotations,
    get_annotations,
)
from .constraints import (
    ArrayConstraint,
    CONSTRAINT_METADATA,
    Constraint,
    NumberConstraint,
    ObjectConstraint,
    StringConstraint,
    _constraints,
    get_constraint,
)

T = TypeVar("T")


@dataclass
class Schema(MetadataMixin):
    annotations: Optional[Annotations] = None
    constraint: Optional[Constraint] = None

    def __post_init__(self):
        self.metadata: Dict[str, Any] = {}
        if self.annotations is not None:
            self.metadata[ANNOTATIONS_METADATA] = self.annotations
        if self.constraint is not None:
            self.metadata[CONSTRAINT_METADATA] = self.constraint

    def validate(self, _obj: T) -> T:
        if self.constraint is not None:
            self.constraint.validate(_obj)
        return _obj

    def __call__(self, obj: T) -> T:
        if self.annotations is not None:
            _annotations[obj] = self.annotations
        if self.constraint is not None:
            _constraints[obj] = self.constraint
        return obj

    @property
    def items_(self) -> Union["Schema", Sequence["Schema"]]:
        assert self.constraint is None or isinstance(self.constraint, ArrayConstraint)
        annotations, constraint = None, None
        if self.annotations is not None:
            annotations = self.annotations.items
        if self.constraint is not None:
            constraint = self.constraint.items
        if isinstance(annotations, Sequence):
            assert isinstance(constraint, Sequence)
            assert len(annotations) == len(constraint)
            return [Schema(a, c) for a, c in zip(annotations, constraint)]
        else:
            assert annotations is None or isinstance(annotations, Annotations)
            assert constraint is None or isinstance(constraint, Constraint)
            return Schema(annotations, constraint)

    @property
    def additional_properties(self) -> "Schema":
        assert self.constraint is None or isinstance(self.constraint, ObjectConstraint)
        annotations, constraint = None, None
        if self.annotations is not None:
            annotations = self.annotations.additional_properties
        if self.constraint is not None:
            constraint = self.constraint.additional_properties
        return Schema(annotations, constraint)


def get_schema(cls: Type) -> Schema:
    return Schema(get_annotations(cls), get_constraint(cls))


_constraint_rewrite = {
    "min": "minimum",
    "max": "maximum",
    "exc_min": "exclusive_minimum",
    "exc_max": "exclusive_maximum",
    "mult_of": "multiple_of",
    "min_len": "min_length",
    "max_len": "max_length",
    "unique": "unique_items",
    "properties": "additional_properties",
}


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    examples: Optional[Sequence[Any]] = None,
    read_only: Optional[bool] = None,
    write_only: Optional[bool] = None
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    examples: Optional[Sequence[Any]] = None,
    read_only: Optional[bool] = None,
    write_only: Optional[bool] = None,
    min: Optional[Number] = None,
    max: Optional[Number] = None,
    exc_min: Optional[Number] = None,
    exc_max: Optional[Number] = None,
    mult_of: Optional[Number] = None
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    examples: Optional[Sequence[Any]] = None,
    read_only: Optional[bool] = None,
    write_only: Optional[bool] = None,
    format: Optional[str] = None,
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    pattern: Optional[str] = None
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    examples: Optional[Sequence[Any]] = None,
    read_only: Optional[bool] = None,
    write_only: Optional[bool] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique: Optional[bool] = None,
    items: Optional[Union[Schema, Sequence[Schema]]] = None
) -> Schema:
    ...


@overload
def schema(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    examples: Optional[Sequence[Any]] = None,
    read_only: Optional[bool] = None,
    write_only: Optional[bool] = None,
    min_properties: Optional[int] = None,
    max_properties: Optional[int] = None,
    properties: Optional[Schema] = None
) -> Schema:
    ...


def schema(**kwargs) -> Schema:
    kwargs_ = {_constraint_rewrite.get(k, k): v for k, v in kwargs.items()}
    annotations_fields = {f.name for f in fields(Annotations)}
    annotations_kwargs = {k: v for k, v in kwargs_.items() if k in annotations_fields}
    constraint_kwargs = {
        k: v for k, v in kwargs_.items() if k not in annotations_kwargs
    }
    if "additional_properties" in annotations_kwargs:
        schema1: Schema = annotations_kwargs["additional_properties"]
        annotations_kwargs["additional_properties"] = schema1.annotations
        constraint_kwargs["additional_properties"] = schema1.constraint
    if "items" in annotations_kwargs:
        schema2: Union[Schema, Sequence[Schema]] = annotations_kwargs["items"]
        if not isinstance(schema2, Sequence):
            annotations_kwargs["items"] = [s.annotations for s in schema2]
            constraint_kwargs["items"] = [s.constraint for s in schema2]
        else:
            assert isinstance(schema2, Schema)
            annotations_kwargs["items"] = schema2.annotations
            constraint_kwargs["items"] = schema2.constraint

    annotations = None
    if annotations_kwargs:
        annotations = Annotations(**annotations_kwargs)

    constraint = None
    if constraint_kwargs:
        for cls in (
            NumberConstraint,
            StringConstraint,
            ArrayConstraint,
            ObjectConstraint,
        ):
            try:
                constraint = cls(**constraint_kwargs)
                break
            except TypeError:
                pass

    return Schema(annotations, constraint)
