from dataclasses import field, make_dataclass
from inspect import getmembers
from typing import Any, Collection, Optional

from graphql import print_schema
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import as_declarative

from apischema import Undefined, deserialize, serialize
from apischema.conversions import dataclass_model
from apischema.graphql import graphql_schema
from apischema.json_schema import serialization_schema
from apischema.metadata import required


def column_type(column: Column) -> Any:
    col_type = column.type.python_type
    return Optional[col_type] if column.nullable else col_type


def column_field(column: Column) -> Any:
    if column.default is not None:
        return column.default
    elif column.server_default is not None:
        return Undefined
    elif column.nullable:
        return None
    else:
        # Put default everywhere to avoid
        return field(default=..., metadata=required)


# Very basic SQLAlchemy support
@as_declarative()
class Base:
    def __init_subclass__(cls):
        columns = getmembers(cls, lambda m: isinstance(m, Column))
        if not columns:
            return

        fields = [
            (column.name or field_name, column_type(column), column_field(column))
            for field_name, column in columns
        ]
        dataclass_model(cls)(make_dataclass(cls.__name__, fields))


class Foo(Base):
    __tablename__ = "foo"
    bar = Column(Integer, primary_key=True)
    baz = Column(String)


foo = deserialize(Foo, {"bar": 0})
assert isinstance(foo, Foo)
assert foo.bar == 0
assert serialize(foo) == {"bar": 0, "baz": None}
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}, "baz": {"type": ["string", "null"]}},
    "required": ["bar"],
    "additionalProperties": False,
}


def foos() -> Optional[Collection[Foo]]:
    ...


schema = graphql_schema(query=[foos])
schema_str = """\
type Query {
  foos: [Foo!]
}

type Foo {
  bar: Int!
  baz: String
}
"""
assert print_schema(schema) == schema_str
