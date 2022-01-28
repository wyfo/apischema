from dataclasses import dataclass

from graphql.utilities import print_schema

from apischema import serializer
from apischema.graphql import graphql_schema
from apischema.json_schema import serialization_schema


@dataclass
class A:
    a: int


@dataclass
class B:
    b: int

    @serializer
    def to_a(self) -> A:
        return A(self.b)


def b() -> B:
    return B(0)


def test_default_conversion_type_name():
    assert (
        print_schema(graphql_schema(query=[b]))
        == """\
type Query {
  b: B!
}

type B {
  a: Int!
}"""
    )
    assert serialization_schema(B, all_refs=True) == {
        "$ref": "#/$defs/B",
        "$defs": {
            "B": {"$ref": "#/$defs/A"},
            "A": {
                "type": "object",
                "properties": {"a": {"type": "integer"}},
                "required": ["a"],
                "additionalProperties": False,
            },
        },
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
    }
    assert serialization_schema(B) == {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
    }
