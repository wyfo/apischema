from dataclasses import dataclass

from graphql import print_schema

from apischema.graphql import graphql_schema


@dataclass
class Foo:
    foo: int


@dataclass
class Bar:
    bar: int


def foo_or_bar() -> Foo | Bar: ...


# union_ref default value is made explicit here
schema = graphql_schema(query=[foo_or_bar], union_name="Or".join)
schema_str = """\
type Query {
  fooOrBar: FooOrBar!
}

union FooOrBar = Foo | Bar

type Foo {
  foo: Int!
}

type Bar {
  bar: Int!
}"""
assert print_schema(schema) == schema_str
