from collections.abc import Mapping, Sequence
from operator import itemgetter
from typing import TypeVar

from apischema import serialize
from apischema.json_schema import serialization_schema

T = TypeVar("T")
Priority = int


def sort_by_priority(values_with_priority: Mapping[T, Priority]) -> Sequence[T]:
    return [k for k, _ in sorted(values_with_priority.items(), key=itemgetter(1))]


assert serialize(
    dict[str, Priority], {"a": 1, "b": 0}, conversions=sort_by_priority
) == ["b", "a"]
assert serialization_schema(dict[str, Priority], conversions=sort_by_priority) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "array",
    "items": {"type": "string"},
}
