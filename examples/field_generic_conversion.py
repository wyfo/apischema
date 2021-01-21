from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from operator import itemgetter
from typing import Generic, TypeVar

from apischema import alias, serialize
from apischema.json_schema import serialization_schema
from apischema.metadata import conversion

T = TypeVar("T")
V = TypeVar("V")


def sort_by_priority(values_with_priority: Mapping[int, T]) -> Sequence[T]:
    return [v for _, v in sorted(values_with_priority.items(), key=itemgetter(0))]


assert sort_by_priority({1: "a", 0: "b"}) == ["b", "a"]


@dataclass
class Foo(Generic[V]):
    values_with_priority: dict[int, V] = field(
        metadata=alias("values") | conversion(serialization=sort_by_priority)
    )


assert serialize(Foo({1: "a", 0: "b"})) == {"values": ["b", "a"]}
assert serialization_schema(Foo[str]) == {
    "type": "object",
    "properties": {"values": {"type": "array", "items": {"type": "string"}}},
    "required": ["values"],
    "additionalProperties": False,
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
}
