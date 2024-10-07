from collections.abc import Collection
from inspect import getmembers
from itertools import starmap
from typing import Any

from graphql import print_schema
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import as_declarative

from apischema import Undefined, deserialize, serialize
from apischema.graphql import graphql_schema
from apischema.json_schema import deserialization_schema
from apischema.objects import ObjectField, set_object_fields


def column_field(name: str, column: Column) -> ObjectField:
    required = False
    default: Any = ...
    if column.default is not None:
        default = column.default
    elif column.server_default is not None:
        default = Undefined
    elif column.nullable:
        default = None
    else:
        required = True
    col_type = column.type.python_type
    if column.nullable:
        col_type = col_type | None
    return ObjectField(column.name or name, col_type, required, default=default)


# Very basic SQLAlchemy support
@as_declarative()
class Base:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        columns = getmembers(cls, lambda m: isinstance(m, Column))
        if not columns:
            return
        set_object_fields(cls, starmap(column_field, columns))


class Foo(Base):
    __tablename__ = "foo"
    bar = Column(Integer, primary_key=True)
    baz = Column(String)


foo = deserialize(Foo, {"bar": 0})
assert isinstance(foo, Foo)
assert foo.bar == 0
assert serialize(Foo, foo) == {"bar": 0, "baz": None}
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "type": "object",
    "properties": {
        "bar": {"type": "integer"},
        "baz": {"type": ["string", "null"], "default": None},
    },
    "required": ["bar"],
    "additionalProperties": False,
}


def foos() -> Collection[Foo] | None: ...


schema = graphql_schema(query=[foos])
schema_str = """\
type Query {
  foos: [Foo!]
}

type Foo {
  bar: Int!
  baz: String
}"""
assert print_schema(schema) == schema_str
