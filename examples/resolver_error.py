from dataclasses import dataclass
from logging import getLogger
from typing import Any

import graphql
from graphql.utilities import print_schema

from apischema.graphql import graphql_schema, resolver

logger = getLogger(__name__)


def log_error(
    error: Exception, obj: Any, info: graphql.GraphQLResolveInfo, **kwargs
) -> None:
    logger.error(
        "Resolve error in %s", ".".join(map(str, info.path.as_list())), exc_info=error
    )
    return None


@dataclass
class Foo:
    @resolver(error_handler=log_error)
    def bar(self) -> int:
        raise RuntimeError("Bar error")

    @resolver
    def baz(self) -> int:
        raise RuntimeError("Baz error")


def foo(info: graphql.GraphQLResolveInfo) -> Foo:
    return Foo()


schema = graphql_schema(query=[foo])
# Notice that bar is Int while baz is Int!
schema_str = """\
type Query {
  foo: Foo!
}

type Foo {
  bar: Int
  baz: Int!
}"""
assert print_schema(schema) == schema_str
# Logs "Resolve error in foo.bar", no error raised
assert graphql.graphql_sync(schema, "{foo{bar}}").data == {"foo": {"bar": None}}
# Error is raised
assert graphql.graphql_sync(schema, "{foo{baz}}").errors[0].message == "Baz error"
