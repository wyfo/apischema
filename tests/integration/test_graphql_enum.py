from enum import Enum

from graphql import graphql_sync
from graphql.utilities import print_schema

from apischema.graphql import graphql_schema


class MyEnum(Enum):
    FOO = "FOO"
    BAR = "BAR"


def echo(enum: MyEnum) -> MyEnum:
    return enum


def test_graphql_enum():
    schema = graphql_schema(query=[echo])
    assert (
        print_schema(schema)
        == """\
type Query {
  echo(enum: MyEnum!): MyEnum!
}

enum MyEnum {
  FOO
  BAR
}
"""
    )
    assert graphql_sync(schema, "{echo(enum: FOO)}").data == {"echo": "FOO"}
