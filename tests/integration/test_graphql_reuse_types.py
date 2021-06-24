from dataclasses import dataclass
from typing import Union
from uuid import UUID

from graphql.utilities import print_schema

from apischema.graphql import graphql_schema


@dataclass
class Foo:
    f: str


@dataclass
class Bar:
    b: int


@dataclass
class Data:
    id: UUID
    foo_bar: Union[Foo, Bar]


def foo_to_data(id: UUID, foo: Foo) -> Data:
    ...


def bar_to_data(id: UUID, bar: Bar) -> Data:
    ...


def test_graphql_reuse_types():
    schema = graphql_schema(query=[foo_to_data, bar_to_data])
    assert (
        print_schema(schema)
        == """\
type Query {
  fooToData(id: UUID!, foo: FooInput!): Data!
  barToData(id: UUID!, bar: BarInput!): Data!
}

type Data {
  id: UUID!
  fooBar: FooOrBar!
}

scalar UUID

union FooOrBar = Foo | Bar

type Foo {
  f: String!
}

type Bar {
  b: Int!
}

input FooInput {
  f: String!
}

input BarInput {
  b: Int!
}
"""
    )
