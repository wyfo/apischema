from dataclasses import dataclass
from uuid import UUID

from graphql import print_schema

from apischema.graphql import graphql_schema


@dataclass
class Foo:
    bar: UUID


def foo() -> Foo | None: ...


# id_types={UUID} is equivalent to id_types=lambda t: t in {UUID}
schema = graphql_schema(query=[foo], id_types={UUID})
schema_str = """\
type Query {
  foo: Foo
}

type Foo {
  bar: ID!
}"""
assert print_schema(schema) == schema_str
