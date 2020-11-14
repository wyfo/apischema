from dataclasses import dataclass, field
from operator import itemgetter
from typing import Dict, Mapping, Sequence, TypeVar

from apischema import alias, serialize
from apischema.json_schema import serialization_schema
from apischema.metadata import conversions

T = TypeVar("T")


def sort_by_priority(values_with_priority: Mapping[int, T]) -> Sequence[T]:
    return [v for _, v in sorted(values_with_priority.items(), key=itemgetter(0))]


assert sort_by_priority({1: "a", 0: "b"}) == ["b", "a"]


@dataclass
class Foo:
    values_with_priority: Dict[int, str] = field(
        metadata=alias("values") | conversions(serializer=sort_by_priority)
    )


assert serialize(Foo({1: "a", 0: "b"})) == {"values": ["b", "a"]}
assert serialization_schema(Foo) == {
    "type": "object",
    "properties": {"values": {"type": "array", "items": {"type": "string"}}},
    "required": ["values"],
    "additionalProperties": False,
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
}
