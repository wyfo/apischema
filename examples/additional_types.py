from dataclasses import dataclass

from graphql import print_schema

from apischema.graphql import graphql_schema, interface


@interface
@dataclass
class Bar:
    bar: int


@dataclass
class Foo(Bar):
    baz: str


def bar() -> Bar: ...


schema = graphql_schema(query=[bar], types=[Foo])
# type Foo would have not been present if Foo was not put in types
schema_str = """\
type Foo implements Bar {
  bar: Int!
  baz: String!
}

interface Bar {
  bar: Int!
}

type Query {
  bar: Bar!
}"""
assert print_schema(schema) == schema_str
