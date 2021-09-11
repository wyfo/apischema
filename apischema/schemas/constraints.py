import operator as op
from collections import defaultdict
from dataclasses import dataclass, field, fields
from math import gcd
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Optional,
    Pattern,
    Tuple,
    TypeVar,
)

from apischema.types import Number
from apischema.utils import merge_opts, to_hashable

T = TypeVar("T")
U = TypeVar("U")

COMPARISON_MERGE_AND_ERRORS: Dict[Callable, Tuple[Callable, str]] = {
    op.lt: (max, "less than %s"),
    op.le: (max, "less than or equal to %s"),
    op.gt: (min, "greater than %s"),
    op.ge: (min, "greater than or equal to %s"),
}
PREFIX_DICT: Mapping[type, str] = {
    str: "string length",
    list: "item count",
    dict: "property count",
}
Check = Callable[[Any, Any], Any]
CONSTRAINT_METADATA_KEY = "constraint"


@dataclass
class ConstraintMetadata:
    alias: str
    cls: type
    check: Check
    error: Callable[[Any], str]
    merge: Callable[[T, T], T]

    @property
    def field(self) -> Any:
        return field(default=None, metadata={CONSTRAINT_METADATA_KEY: self})


def comparison(alias: str, cls: type, check: Check) -> Any:
    merge, error = COMPARISON_MERGE_AND_ERRORS[check]
    prefix = PREFIX_DICT.get(cls)  # type: ignore
    if prefix:
        error = prefix + " " + error.replace("less", "lower")
    if cls in (str, list, dict):
        wrapped = check

        def check(data: Any, value: Any) -> bool:
            return wrapped(len(data), value)

    return ConstraintMetadata(alias, cls, check, lambda v: error % v, merge).field


def merge_mult_of(m1: Number, m2: Number) -> Number:
    if not isinstance(m1, int) and not isinstance(m2, int):
        raise TypeError("multipleOf merging is only supported with integers")
    return m1 * m2 / gcd(m1, m2)  # type: ignore


def not_match_pattern(data: str, pattern: Pattern) -> bool:
    return not pattern.match(data)


def merge_pattern(p1: Pattern, p2: Pattern) -> Pattern:
    raise TypeError("Cannot merge patterns")


def not_unique(data: list, unique: bool) -> bool:
    return (op.ne if unique else op.eq)(len(set(map(to_hashable, data))), len(data))


@dataclass(frozen=True)
class Constraints:
    # number
    min: Optional[Number] = comparison("minimum", float, op.lt)
    max: Optional[Number] = comparison("maximum", float, op.gt)
    exc_min: Optional[Number] = comparison("exclusiveMinimum", float, op.le)
    exc_max: Optional[Number] = comparison("exclusiveMaximum", float, op.ge)
    mult_of: Optional[Number] = ConstraintMetadata(
        "multipleOf", float, op.mod, lambda n: f"not a multiple of {n}", merge_mult_of  # type: ignore
    ).field
    # string
    min_len: Optional[int] = comparison("minLength", str, op.lt)
    max_len: Optional[int] = comparison("maxLength", str, op.gt)
    pattern: Optional[Pattern] = ConstraintMetadata(
        "pattern",
        str,
        not_match_pattern,
        lambda p: f"not matching '{p.pattern}'",
        merge_pattern,  # type: ignore
    ).field
    # array
    min_items: Optional[int] = comparison("minItems", list, op.lt)
    max_items: Optional[int] = comparison("maxItems", list, op.gt)
    unique: Optional[bool] = ConstraintMetadata(
        "uniqueItems", list, not_unique, lambda _: "duplicate items", op.or_
    ).field
    # object
    min_props: Optional[int] = comparison("minProperties", dict, op.lt)
    max_props: Optional[int] = comparison("maxProperties", dict, op.gt)

    @property
    def attr_and_metata(
        self,
    ) -> Collection[Tuple[str, Optional[Any], ConstraintMetadata]]:
        return [
            (f.name, getattr(self, f.name), f.metadata[CONSTRAINT_METADATA_KEY])
            for f in fields(self)
            if CONSTRAINT_METADATA_KEY in f.metadata
        ]

    @property
    def checks_by_type(self) -> Mapping[type, Collection[Tuple[Check, Any, str]]]:
        result = defaultdict(list)
        for _, attr, metadata in self.attr_and_metata:
            if attr is None:
                continue
            error = f"{metadata.error(attr)} ({metadata.alias})"
            result[metadata.cls].append((metadata.check, attr, error))
        result[int] = result[float]
        return result

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
