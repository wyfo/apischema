import re
from dataclasses import InitVar, dataclass, field, fields
from math import gcd
from operator import or_
from typing import (
    Any,
    Callable,
    ClassVar,
    Collection,
    Dict,
    Iterator,
    Mapping,
    Optional,
    Pattern,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.types import Number
from apischema.utils import to_hashable
from apischema.validation.errors import ValidationError

MERGE_METADATA = "merge"

T = TypeVar("T")


def merge(operation: Callable[[Any, Any], Any], *, init=True) -> Optional[Any]:
    return field(default=None, init=init, metadata={MERGE_METADATA: operation})


_Constraints = TypeVar("_Constraints", bound="Constraints")


@dataclass(frozen=True)
class Constraints:
    valid_types: ClassVar[Union[Type, Tuple[Type, ...]]] = object
    _cache: ClassVar[Dict["Constraints", "Constraints"]]

    def _validate(self, data) -> Iterator[str]:
        yield from ()

    def validate(self, data: T) -> T:
        errors = list(self._validate(data))
        if errors:
            raise ValidationError(errors)
        return data

    def merge(self: _Constraints, other: Optional[_Constraints]) -> _Constraints:
        if other is None:
            return self
        try:
            return self._cache[other]  # type: ignore
        except (KeyError, AttributeError):
            if type(other) != type(self):
                raise TypeError("Incompatible constraints types")
            constraints: Dict[str, Any] = {}
            for field_ in fields(self):
                if getattr(self, field_.name) is None:
                    constraints[field_.name] = getattr(other, field_.name)
                elif getattr(other, field_.name) is None:
                    constraints[field_.name] = getattr(self, field_.name)
                else:
                    constraints[field_.name] = field_.metadata[MERGE_METADATA](
                        getattr(self, field_.name), getattr(other, field_.name)
                    )
            result = type(self)(**constraints)  # type: ignore
            if not hasattr(self, "_cache"):
                super().__setattr__("_cache", {})
            self._cache[other] = result
            return result


_constraints: Dict[Any, Constraints] = {}

get_constraints = _constraints.get

Cls = TypeVar("Cls", bound=type)


@dataclass(frozen=True)
class NumberConstraints(Constraints):
    valid_types = (int, float)
    minimum: Optional[Number] = merge(max)
    maximum: Optional[Number] = merge(min)
    exclusive_minimum: Optional[Number] = merge(min)
    exclusive_maximum: Optional[Number] = merge(max)
    multiple_of: Optional[Number] = merge(lambda m1, m2: m1 * m2 / gcd(m1, m2))

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, self.valid_types)
        if self.minimum is not None and data < self.minimum:
            yield f"less than {self.minimum} (minimum)"
        if self.maximum is not None and data > self.maximum:
            yield f"greater than {self.maximum} (maximum)"
        if self.exclusive_minimum is not None and data <= self.exclusive_minimum:
            yield f"less than or equal to {self.exclusive_minimum} (exclusiveMinimum)"
        if self.exclusive_maximum is not None and data >= self.exclusive_maximum:
            yield f"greater than or equal to {self.exclusive_maximum} (exclusiveMaximum)"  # noqa: E501
        if self.multiple_of is not None and (data % self.multiple_of) != 0:
            yield f"not a multiple of {self.multiple_of} (multipleOf)"


def merge_pattern(p1: Pattern, p2: Pattern) -> Pattern:
    raise TypeError("Cannot merge patterns")


@dataclass(frozen=True)
class StringConstraints(Constraints):
    valid_types = str
    min_length: Optional[int] = merge(max)
    max_length: Optional[int] = merge(min)
    pattern: InitVar[Optional[Union[str, Pattern]]] = merge(merge_pattern)
    _pattern: Optional[Pattern] = field(init=False)

    def __post_init__(self, pattern: Optional[Union[str, Pattern]]):
        super().__setattr__(
            "_pattern", re.compile(pattern) if pattern is not None else None
        )

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, self.valid_types)
        if self.min_length is not None and len(data) < self.min_length:
            yield f"length less than {self.min_length} (minLength)"
        if self.max_length is not None and len(data) > self.max_length:
            yield f"length greater than {self.max_length} (maxLength)"
        if self._pattern is not None and not re.match(self._pattern, data):
            yield f"unmatched pattern '{self._pattern.pattern}'"


@dataclass(frozen=True)
class ArrayConstraints(Constraints):
    valid_types = Collection
    min_items: Optional[int] = merge(max)
    max_items: Optional[int] = merge(min)
    unique_items: Optional[bool] = merge(or_)

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, self.valid_types)
        if self.min_items is not None and len(data) < self.min_items:
            yield f"size less than {self.min_items} (minItems)"
        if self.max_items is not None and len(data) > self.max_items:
            yield f"size greater than {self.max_items} (maxItems)"
        if self.unique_items is not None:
            if len(set(map(to_hashable, data))) != len(data):
                yield "duplicate items (uniqueItems)"


@dataclass(frozen=True)
class ObjectConstraints(Constraints):
    valid_types = Mapping
    min_properties: Optional[int] = merge(max)
    max_properties: Optional[int] = merge(min)

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, self.valid_types)
        if self.min_properties is not None and len(data) < self.min_properties:
            yield f"size less than {self.min_properties} (minProperties)"
        if self.max_properties is not None and len(data) > self.max_properties:
            yield f"size greater than {self.max_properties} (maxProperties)"
