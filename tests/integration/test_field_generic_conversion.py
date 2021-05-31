from dataclasses import dataclass, field
from operator import itemgetter
from typing import Dict, Generic, Mapping, Sequence, TypeVar

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
    values_with_priority: Dict[int, V] = field(
        metadata=alias("values") | conversion(serialization=sort_by_priority)
    )


def test_field_generic_conversion():
    assert serialize(Foo[str], Foo({1: "a", 0: "b"})) == {"values": ["b", "a"]}
    assert serialization_schema(Foo[str]) == {
        "type": "object",
        "properties": {"values": {"type": "array", "items": {"type": "string"}}},
        "required": ["values"],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
    }
