from dataclasses import dataclass
from typing import Callable, ClassVar

from graphql.utilities import print_schema

from apischema.graphql import graphql_schema, resolver
from apischema.json_schema import serialization_schema


@dataclass
class A:
    a: int
    b: ClassVar[Callable]
    _: ClassVar[Callable]

    @resolver(serialized=True)  # type: ignore
    def b(self) -> int:
        ...

    @resolver("c", serialized=True)  # type: ignore
    def _(self) -> int:
        ...

    d: int


@dataclass
class B(A):
    e: int


def query() -> B:
    ...


def test_resolver_position():
    assert serialization_schema(B) == {
        "type": "object",
        "properties": {
            "a": {"type": "integer"},
            "b": {"readOnly": True, "type": "integer"},
            "c": {"readOnly": True, "type": "integer"},
            "d": {"type": "integer"},
            "e": {"type": "integer"},
        },
        "required": ["a", "b", "c", "d", "e"],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
    }
    assert (
        print_schema(graphql_schema(query=[query]))
        == """\
type Query {
  query: B!
}

type B {
  a: Int!
  b: Int!
  c: Int!
  d: Int!
  e: Int!
}
"""
    )
