from dataclasses import dataclass, field
from typing import Generic, TypeVar

from apischema import type_name
from apischema.json_schema import deserialization_schema
from apischema.metadata import flatten

T = TypeVar("T")

# Type name factory takes the type and its arguments as (positional) parameters
@type_name(lambda tp, arg: f"{arg.__name__}Resource")
@dataclass
class Resource(Generic[T]):
    id: int
    content: T = field(metadata=flatten)
    ...


@dataclass
class Foo:
    bar: str


assert deserialization_schema(Resource[Foo], all_refs=True) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$ref": "#/$defs/FooResource",
    "$defs": {
        "FooResource": {
            "type": "object",
            "allOf": [
                {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                    "additionalProperties": False,
                },
                {"$ref": "#/$defs/Foo"},
            ],
            "unevaluatedProperties": False,
        },
        "Foo": {
            "type": "object",
            "properties": {"bar": {"type": "string"}},
            "required": ["bar"],
            "additionalProperties": False,
        },
    },
}
