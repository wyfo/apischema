import operator as op
from dataclasses import dataclass, field, fields
from math import gcd
from typing import Any, Callable, Collection, Dict, Optional, Pattern, Tuple, TypeVar

from apischema.types import Number
from apischema.utils import merge_opts

T = TypeVar("T")
U = TypeVar("U")

CONSTRAINT_METADATA_KEY = "constraint"


@dataclass
class ConstraintMetadata:
    alias: str
    cls: type
    merge: Callable[[T, T], T]

    @property
    def field(self) -> Any:
        return field(default=None, metadata={CONSTRAINT_METADATA_KEY: self})


def constraint(alias: str, cls: type, merge: Callable[[T, T], T]) -> Any:
    return field(
        default=None,
        metadata={CONSTRAINT_METADATA_KEY: ConstraintMetadata(alias, cls, merge)},
    )


def merge_mult_of(m1: Number, m2: Number) -> Number:
    if not isinstance(m1, int) and not isinstance(m2, int):
        raise TypeError("multipleOf merging is only supported with integers")
    return m1 * m2 / gcd(m1, m2)  # type: ignore


def merge_pattern(p1: Pattern, p2: Pattern) -> Pattern:
    raise TypeError("Cannot merge patterns")


min_, max_ = min, max


@dataclass(frozen=True)
class Constraints:
    # number
    min: Optional[Number] = constraint("minimum", float, max_)
    max: Optional[Number] = constraint("maximum", float, min_)
    exc_min: Optional[Number] = constraint("exclusiveMinimum", float, max_)
    exc_max: Optional[Number] = constraint("exclusiveMaximum", float, min_)
    mult_of: Optional[Number] = constraint("multipleOf", float, merge_mult_of)
    # string
    min_len: Optional[int] = constraint("minLength", str, max_)
    max_len: Optional[int] = constraint("maxLength", str, min_)
    pattern: Optional[Pattern] = constraint("pattern", str, merge_pattern)
    # array
    min_items: Optional[int] = constraint("minItems", list, max_)
    max_items: Optional[int] = constraint("maxItems", list, min_)
    unique: Optional[bool] = constraint("uniqueItems", list, op.or_)
    # object
    min_props: Optional[int] = constraint("minProperties", dict, max_)
    max_props: Optional[int] = constraint("maxProperties", dict, min_)

    @property
    def attr_and_metata(
        self,
    ) -> Collection[Tuple[str, Optional[Any], ConstraintMetadata]]:
        return [
            (f.name, getattr(self, f.name), f.metadata[CONSTRAINT_METADATA_KEY])
            for f in fields(self)
            if CONSTRAINT_METADATA_KEY in f.metadata
        ]

    def merge_into(self, base_schema: Dict[str, Any]):
        for name, attr, metadata in self.attr_and_metata:
            if attr is not None:
                alias = metadata.alias
                if alias in base_schema:
                    base_schema[alias] = metadata.merge(attr, base_schema[alias])  # type: ignore
                else:
                    base_schema[alias] = attr


@merge_opts
def merge_constraints(c1: Constraints, c2: Constraints) -> Constraints:
    constraints: Dict[str, Any] = {}
    for name, attr1, metadata in c1.attr_and_metata:
        attr2 = getattr(c2, name)
        if attr1 is None:
            constraints[name] = attr2
        elif attr2 is None:
            constraints[name] = attr1
        else:
            constraints[name] = metadata.merge(attr1, attr2)  # type: ignore
    return Constraints(**constraints)  # type: ignore
