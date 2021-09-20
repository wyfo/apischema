from dataclasses import dataclass

from apischema.json_schema import deserialization_schema, serialization_schema


@dataclass
class Foo:
    bar: str


assert deserialization_schema(Foo) == serialization_schema(Foo)
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "additionalProperties": False,
    "properties": {"bar": {"type": "string"}},
    "required": ["bar"],
    "type": "object",
}
