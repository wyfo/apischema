import re
from typing import Any, Dict, Iterator, Optional, Pattern, Sequence, TypeVar, Union

from dataclasses import dataclass

from apischema.types import Number
from apischema.utils import PREFIX, to_hashable
from apischema.validation.errors import ValidationError

CONSTRAINT_METADATA = f"{PREFIX}constraint"

T = TypeVar("T")


@dataclass
class Constraint:
    read_only: Optional[bool] = None
    write_only: Optional[bool] = None

    def __post_init__(self):
        if self.read_only is not None and self.write_only is not None:
            raise ValueError("Schema cannot be both read/write only")

    def _validate(self, data) -> Iterator[str]:
        raise NotImplementedError()

    def validate(self, data: T) -> T:
        errors = list(self._validate(data))
        if errors:
            raise ValidationError(errors)
        return data


_constraints: Dict[Any, Constraint] = {}

get_constraint = _constraints.get

Cls = TypeVar("Cls", bound=type)


@dataclass
class NumberConstraint(Constraint):
    minimum: Optional[Number] = None
    maximum: Optional[Number] = None
    exclusive_minimum: Optional[Number] = None
    exclusive_maximum: Optional[Number] = None
    multiple_of: Optional[Number] = None

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, (int, float))
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


@dataclass
class StringConstraint(Constraint):
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[Union[str, Pattern]] = None

    def __post_init__(self):
        super().__post_init__()
        if self.pattern is not None:
            self.pattern = re.compile(self.pattern)

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, str)
        if self.min_length is not None and len(data) < self.min_length:
            yield f"length less than {self.min_length} (minLength)"
        if self.max_length is not None and len(data) > self.max_length:
            yield f"length greater than {self.max_length} (maxLength)"
        if self.pattern is not None and not re.fullmatch(self.pattern, data):
            yield f"unmatched pattern '{self.pattern}'"


@dataclass
class ArrayConstraint(Constraint):
    min_items: Optional[int] = None
    max_items: Optional[int] = None
    items: Optional[Union[Constraint, Sequence[Constraint]]] = None
    unique_items: Optional[bool] = None

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, list)
        if self.min_items is not None and len(data) < self.min_items:
            yield f"size less than {self.min_items} (minItems)"
        if self.max_items is not None and len(data) > self.max_items:
            yield f"size greater than {self.max_items} (maxItems)"
        if self.unique_items and len(set(map(to_hashable, data))) != len(data):
            yield "duplicate items (uniqueItems)"


@dataclass
class ObjectConstraint(Constraint):
    min_properties: Optional[int] = None
    max_properties: Optional[int] = None
    additional_properties: Optional[Constraint] = None

    def _validate(self, data: Any) -> Iterator[str]:
        assert isinstance(data, dict)
        if self.min_properties is not None and len(data) < self.min_properties:
            yield f"size less than {self.min_properties} (minProperties)"
        if self.max_properties is not None and len(data) > self.max_properties:
            yield f"size greater than {self.max_properties} (maxProperties)"
