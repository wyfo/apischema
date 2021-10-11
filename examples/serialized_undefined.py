from dataclasses import dataclass

from apischema import Undefined, UndefinedType, serialize, serialized
from apischema.json_schema import serialization_schema


@dataclass
class Foo:
    @serialized
    def bar(self) -> int | UndefinedType:
        return Undefined


assert serialize(Foo, Foo()) == {}
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "additionalProperties": False,
}
