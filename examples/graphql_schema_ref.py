from dataclasses import dataclass
from typing import Optional

from graphql import print_schema

from apischema import schema_ref
from apischema.graphql import graphql_schema


@schema_ref("Baz")
@dataclass
class Foo:
    bar: int


def foo() -> Optional[Foo]:
    ...


schema = graphql_schema(query=[foo])
schema_str = """\
type Query {
  foo: Baz
}

type Baz {
  bar: Int!
}
"""
assert print_schema(schema) == schema_str
