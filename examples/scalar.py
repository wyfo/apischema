from dataclasses import dataclass
from typing import Any
from uuid import UUID

from graphql.utilities import print_schema

from apischema.graphql import graphql_schema


@dataclass
class Foo:
    id: UUID
    content: Any


def foo() -> Foo | None: ...


schema = graphql_schema(query=[foo])
schema_str = """\
type Query {
  foo: Foo
}

type Foo {
  id: UUID!
  content: JSON
}

scalar UUID

scalar JSON"""
assert print_schema(schema) == schema_str
