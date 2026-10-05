import inspect
from dataclasses import dataclass
from typing import Any, Callable

import docstring_parser
from graphql.utilities import print_schema

from apischema import schema, settings
from apischema.graphql import graphql_schema, resolver
from apischema.schemas import Schema


@dataclass
class Foo:
    @resolver
    def bar(self, arg: str) -> int:
        """bar method

        :param arg: arg parameter
        """
        ...


def method_base_schema(tp: Any, method: Callable, alias: str) -> Schema | None:
    return schema(description=docstring_parser.parse(method.__doc__).short_description)


def parameter_base_schema(
    method: Callable, parameter: inspect.Parameter, alias: str
) -> Schema | None:
    for doc_param in docstring_parser.parse(method.__doc__).params:
        if doc_param.arg_name == parameter.name:
            return schema(description=doc_param.description)
    return None


settings.base_schema.method = method_base_schema
settings.base_schema.parameter = parameter_base_schema


def foo() -> Foo: ...


schema_ = graphql_schema(query=[foo])
schema_str = '''\
type Query {
  foo: Foo!
}

type Foo {
  """bar method"""
  bar(
    """arg parameter"""
    arg: String!
  ): Int!
}'''
assert print_schema(schema_) == schema_str
