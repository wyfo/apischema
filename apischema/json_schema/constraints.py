import operator
import re
from dataclasses import dataclass, field, fields
from math import gcd
from typing import (
    Any,
    Callable,
    ClassVar,
    Collection,
    Dict,
    List,
    Mapping,
    Optional,
    Pattern,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.types import Number
from apischema.utils import merge_opts, to_hashable
from apischema.validation.errors import ValidationError

VALIDATION_METADATA = "validation"
MODIFIER_METADATA = "modifier"
MERGE_METADATA = "merge"
ALIAS_METADATA = "alias"

T = TypeVar("T")


def comparison_field(comparison: Callable, alias: str = None):
    by_comp = {
        operator.lt: (max, "less than"),
        operator.le: (max, "less than or equal to"),
        operator.gt: (min, "greater than"),
        operator.ge: (min, "greater than or equal to"),
    }
    merge, err = by_comp[comparison]
    metadata = {
        VALIDATION_METADATA: (comparison, err + " {}"),
        MODIFIER_METADATA: ...,
        MERGE_METADATA: merge,
    }
    if alias is not None:
        metadata[ALIAS_METADATA] = alias
    return field(default=None, metadata=metadata)


_Constraints = TypeVar("_Constraints", bound="Constraints")


@dataclass(frozen=True)
class Constraints:
    valid_types: ClassVar[Union[Type, Tuple[Type, ...]]]
    collection_prefix: ClassVar[Optional[str]] = None

    def __post_init__(self):
        checks: List[Tuple[Any, Callable, Callable, str]] = []
        for f in fields(self):
            attr = getattr(self, f.name)
            if attr is None:
                continue
            comp, err = f.metadata[VALIDATION_METADATA]
            error = err.format(attr) + f" ({f.metadata.get(ALIAS_METADATA, f.name)})"
            modif = f.metadata.get(MODIFIER_METADATA)
            if modif is ...:
                if self.collection_prefix is not None:
                    error = f"{self.collection_prefix} {error}"
                    modif = len
                else:
                    modif = None
            if modif is None:
                modif = lambda x: x  # noqa: E731
            checks.append((attr, comp, modif, error))

        def errors(data: Any) -> List[str]:
            assert isinstance(data, self.valid_types)
            return [err for attr, comp, modif, err in checks if comp(modif(data), attr)]

        object.__setattr__(self, self.errors.__name__, errors)

    def validate(self, data: T) -> T:
        errors = self.errors(data)
        if errors:
            raise ValidationError(errors)
        return data

    def errors(self, data: Any) -> List[str]:
        raise NotImplementedError  # initialized in __post_init__

    def as_dict(self) -> Mapping[str, Any]:
        return {
            f.metadata.get(ALIAS_METADATA, f.name): getattr(self, f.name)
            for f in fields(self)
            if getattr(self, f.name) is not None
        }


Cls = TypeVar("Cls", bound=type)


@dataclass(frozen=True)
class NumberConstraints(Constraints):
    valid_types = (int, float)
    min: Optional[Number] = comparison_field(operator.lt, "minimum")
    max: Optional[Number] = comparison_field(operator.gt, "maximum")
    exc_min: Optional[Number] = comparison_field(operator.le, "exclusiveMinimum")
    exc_max: Optional[Number] = comparison_field(operator.ge, "exclusiveMaximum")
    mult_of: Optional[Number] = field(
        default=None,
        metadata={
            VALIDATION_METADATA: (operator.mod, "not a multiple of {}"),
            MERGE_METADATA: lambda m1, m2: m1 * m2 / gcd(m1, m2),
            ALIAS_METADATA: "multipleOf",
        },
    )


def merge_pattern(p1: Pattern, p2: Pattern) -> Pattern:
    raise TypeError("Cannot merge patterns")


class PatternNotMatched(str):
    def format(self, arg: Pattern) -> str:  # type: ignore
        return f"'{arg.pattern}' not matched"


@dataclass(frozen=True)
class StringConstraints(Constraints):
    valid_types = str
    collection_prefix = "length"
    min_len: Optional[int] = comparison_field(operator.lt, "minLength")
    max_len: Optional[int] = comparison_field(operator.gt, "maxLength")
    pattern: Optional[Union[str, Pattern]] = field(
        default=None,
        metadata={
            VALIDATION_METADATA: (lambda d, p: not p.match(d), PatternNotMatched()),
            MERGE_METADATA: merge_pattern,
        },
    )

    def __post_init__(self):
        if self.pattern is not None:
            object.__setattr__(self, "pattern", re.compile(self.pattern))
        super().__post_init__()


@dataclass(frozen=True)
class ArrayConstraints(Constraints):
    valid_types = Collection
    collection_prefix = "size"
    min_items: Optional[int] = comparison_field(operator.lt, "minItems")
    max_items: Optional[int] = comparison_field(operator.gt, "maxItems")
    unique: Optional[bool] = field(
        default=None,
        metadata={
            VALIDATION_METADATA: (operator.ne, "duplicate items"),
            MODIFIER_METADATA: lambda d: len(set(map(to_hashable, d))) == len(d),
            MERGE_METADATA: operator.or_,
            ALIAS_METADATA: "uniqueItems",
        },
    )


@dataclass(frozen=True)
class ObjectConstraints(Constraints):
    valid_types = Mapping
    collection_prefix = "size"
    min_props: Optional[int] = comparison_field(operator.lt, "minProperties")
    max_props: Optional[int] = comparison_field(operator.gt, "maxProperties")


@merge_opts
def merge_constraints(c1: Constraints, c2: Constraints) -> Constraints:
    if type(c2) != type(c1):
        raise TypeError("Incompatible constraints types")
    constraints: Dict[str, Any] = {}
    for field_ in fields(c1):
        if getattr(c1, field_.name) is None:
            constraints[field_.name] = getattr(c2, field_.name)
        elif getattr(c2, field_.name) is None:
            constraints[field_.name] = getattr(c1, field_.name)
        else:
            constraints[field_.name] = field_.metadata[MERGE_METADATA](
                getattr(c1, field_.name), getattr(c2, field_.name)
            )
    return type(c1)(**constraints)  # type: ignore
