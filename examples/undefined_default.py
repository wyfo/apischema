from graphql import graphql_sync

from apischema import Undefined, UndefinedType
from apischema.graphql import graphql_schema


def arg_is_absent(arg: int | UndefinedType | None = Undefined) -> bool:
    return arg is Undefined


schema = graphql_schema(query=[arg_is_absent])
assert graphql_sync(schema, "{argIsAbsent(arg: null)}").data == {"argIsAbsent": False}
assert graphql_sync(schema, "{argIsAbsent}").data == {"argIsAbsent": True}
