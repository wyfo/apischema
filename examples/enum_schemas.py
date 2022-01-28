from enum import Enum

from graphql import graphql_sync
from graphql.utilities import print_schema

from apischema import schema
from apischema.graphql import graphql_schema


class MyEnum(Enum):
    FOO = "FOO"
    BAR = "BAR"


def echo(enum: MyEnum) -> MyEnum:
    return enum


schema_ = graphql_schema(
    query=[echo], enum_schemas={MyEnum.FOO: schema(description="foo")}
)
schema_str = '''\
type Query {
  echo(enum: MyEnum!): MyEnum!
}

enum MyEnum {
  """foo"""
  FOO
  BAR
}'''
assert print_schema(schema_) == schema_str
assert graphql_sync(schema_, "{echo(enum: FOO)}").data == {"echo": "FOO"}
