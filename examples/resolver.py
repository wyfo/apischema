from dataclasses import dataclass

from graphql import print_schema

from apischema.graphql import graphql_schema, resolver


@dataclass
class Bar:
    baz: int


@dataclass
class Foo:
    @resolver
    async def bar(self, arg: int = 0) -> Bar: ...


async def foo() -> Foo | None: ...


schema = graphql_schema(query=[foo])
schema_str = """\
type Query {
  foo: Foo
}

type Foo {
  bar(arg: Int! = 0): Bar!
}

type Bar {
  baz: Int!
}"""
assert print_schema(schema) == schema_str
