from dataclasses import dataclass

from graphql import print_schema

from apischema.graphql import Query, graphql_schema, resolver


@dataclass
class Foo:
    @resolver
    async def bar(self, arg: int = 0) -> str: ...


async def get_foo() -> Foo: ...


schema = graphql_schema(query=[Query(get_foo, alias="foo", error_handler=None)])
schema_str = """\
type Query {
  foo: Foo
}

type Foo {
  bar(arg: Int! = 0): String!
}"""
assert print_schema(schema) == schema_str
