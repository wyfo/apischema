from dataclasses import make_dataclass
from inspect import getmembers

from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import as_declarative

from apischema import Undefined, deserialize, serialize
from apischema.conversions.dataclass_model import dataclass_model
from apischema.json_schema import serialization_schema


# Very basic SQLAlchemy support
@as_declarative()
class Base:
    def __init_subclass__(cls):
        columns = getmembers(cls, lambda m: isinstance(m, Column))
        if not columns:
            return

        fields = [
            (column.name or field_name, column.type.python_type, Undefined)
            for field_name, column in columns
        ]
        dataclass_model(cls)(make_dataclass(cls.__name__, fields))


class A(Base):
    __tablename__ = "a"
    key = Column(Integer, primary_key=True)


a = deserialize(A, {"key": 0})
assert isinstance(a, A)
assert a.key == 0
assert serialize(a) == {"key": 0}
assert serialization_schema(A) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"key": {"type": "integer"}},
    "additionalProperties": False,
}
