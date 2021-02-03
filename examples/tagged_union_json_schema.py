from dataclasses import dataclass

from apischema.json_schema import deserialization_schema, serialization_schema
from apischema.tagged_unions import Tagged, TaggedUnion


@dataclass
class Bar:
    field: str


class Foo(TaggedUnion):
    bar: Tagged[Bar]
    baz: Tagged[int]


assert (
    deserialization_schema(Foo)
    == serialization_schema(Foo)
    == {
        "type": "object",
        "oneOf": [
            {
                "properties": {
                    "bar": {
                        "type": "object",
                        "properties": {"field": {"type": "string"}},
                        "required": ["field"],
                        "additionalProperties": False,
                    }
                }
            },
            {"properties": {"baz": {"type": "integer"}}},
        ],
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
    }
)
