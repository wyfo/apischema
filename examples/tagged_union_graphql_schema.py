from dataclasses import dataclass

from graphql import graphql_sync
from graphql.utilities import print_schema

from apischema.graphql import graphql_schema
from apischema.tagged_unions import Tagged, TaggedUnion


@dataclass
class Bar:
    field: str


class Foo(TaggedUnion):
    bar: Tagged[Bar]
    baz: Tagged[int]


def query(foo: Foo) -> Foo:
    return foo


schema = graphql_schema(query=[query])
schema_str = """\
type Query {
  query(foo: FooInput!): Foo!
}

type Foo {
  bar: Bar
  baz: Int
}

type Bar {
  field: String!
}

input FooInput {
  bar: BarInput
  baz: Int
}

input BarInput {
  field: String!
}"""
assert print_schema(schema) == schema_str

query_str = """
{
    query(foo: {bar: {field: "value"}}) {
        bar {
            field
        }
        baz
    }
}"""
assert graphql_sync(schema, query_str).data == {
    "query": {"bar": {"field": "value"}, "baz": None}
}
