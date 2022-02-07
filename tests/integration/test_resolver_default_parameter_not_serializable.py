from functools import wraps
from typing import Union

import pytest
from graphql import graphql_sync
from graphql.utilities import print_schema

from apischema import Undefined, UndefinedType, Unsupported
from apischema.graphql import graphql_schema
from apischema.typing import Annotated


class Foo:
    pass


@pytest.mark.parametrize(
    "tp, default",
    [
        (Union[UndefinedType, int], Undefined),
        (Union[int, Annotated[Foo, Unsupported]], Foo()),
    ],
)
def test_resolver_default_parameter_not_serializable(tp, default):
    def resolver(arg=default) -> bool:
        return arg is default

    resolver.__annotations__["arg"] = tp
    # wraps in order to trigger the bug of get_type_hints with None default value
    resolver2 = wraps(resolver)(lambda arg=default: resolver(arg))
    schema = graphql_schema(query=[resolver2])
    assert (
        print_schema(schema)
        == """\
type Query {
  resolver(arg: Int): Boolean!
}"""
    )
    assert (
        graphql_sync(schema, "{resolver}").data
        == graphql_sync(schema, "{resolver(arg: null)}").data
        == {"resolver": True}
    )
