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
    logger.error("Resolve error in %s", ".".join(info.path.as_list()), exc_info=error)
    return None


@dataclass
class Foo:
    @resolver(error_handler=log_error)
    def bar(self) -> int:
        raise RuntimeError("Some error")


def foo() -> Foo:
    return Foo()


schema = graphql_schema(query=[foo])
# Without error_handler (which returns None), it would be 'bar: Int!'
schema_str = """\
type Query {
  foo: Foo!
}

type Foo {
  bar: Int
}
"""
assert print_schema(schema) == schema_str
assert graphql.graphql_sync(schema, "{foo{bar}}").data == {"foo": {"bar": None}}
# Logs "Resolve error in foo.bar"
