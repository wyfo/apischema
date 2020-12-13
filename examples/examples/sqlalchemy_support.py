from dataclasses import MISSING, make_dataclass
from inspect import getmembers
from typing import Collection

from graphql import print_schema
from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import as_declarative

from apischema import Undefined, deserialize, serialize
from apischema.conversions.dataclass_model import dataclass_model
from apischema.graphql import graphql_schema
from apischema.json_schema import serialization_schema


def has_default(column: Column) -> bool:
    return (
        column.nullable
        or column.default is not None
        or column.server_default is not None
    )


# Very basic SQLAlchemy support
@as_declarative()
class Base:
    def __init_subclass__(cls):
        columns = getmembers(cls, lambda m: isinstance(m, Column))
        if not columns:
            return

        fields = [
            (
                column.name or field_name,
                column.type.python_type,
                Undefined if has_default(column) else MISSING,
            )
            for field_name, column in columns
        ]
        dataclass_model(cls)(make_dataclass(cls.__name__, fields))


class Foo(Base):
    __tablename__ = "foo"
    bar = Column(Integer, primary_key=True)


foo = deserialize(Foo, {"bar": 0})
assert isinstance(foo, Foo)
assert foo.bar == 0
assert serialize(foo) == {"bar": 0}
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "required": ["bar"],
    "additionalProperties": False,
}


def foos() -> Collection[Foo]:
    ...


schema = graphql_schema(query=[foos])
schema_str = """\
type Query {
  foos: [Foo!]
}

type Foo {
  bar: Int!
}
"""
assert print_schema(schema) == schema_str
