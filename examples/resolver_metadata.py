from dataclasses import dataclass
from typing import Annotated

from graphql.utilities import print_schema

from apischema import alias, schema
from apischema.graphql import graphql_schema, resolver


@dataclass
class Foo:
    @resolver
    def bar(
        self, param: Annotated[int, alias("arg") | schema(description="argument")]
    ) -> int:
        return param


def foo() -> Foo:
    return Foo()


schema_ = graphql_schema(query=[foo])
# Notice that bar is Int while baz is Int!
schema_str = '''\
type Query {
  foo: Foo!
}

type Foo {
  bar(
    """argument"""
    arg: Int!
  ): Int!
}'''
assert print_schema(schema_) == schema_str
