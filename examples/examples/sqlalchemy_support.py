from dataclasses import fields, make_dataclass
from inspect import getmembers

from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import as_declarative

from apischema import Undefined, deserialize, deserializer, serialize, serializer


# Very basic SQLAlchemy support
@as_declarative()
class Base:
    def __init_subclass__(cls):
        columns = getmembers(cls, lambda m: isinstance(m, Column))
        if not columns:
            return
        dataclass = make_dataclass(
            cls.__name__,
            [(col.name or f, col.type.python_type, Undefined) for f, col in columns],
        )
        field_names = [f.name for f in fields(dataclass)]

        def from_data(data):
            return cls(**{name: getattr(data, name) for name in field_names})

        def to_data(obj):
            return dataclass(**{f: getattr(obj, f) for f, _ in columns})

        deserializer(from_data, dataclass, cls)
        serializer(to_data, cls, dataclass)


class A(Base):
    __tablename__ = "a"
    key = Column(Integer, primary_key=True)


a = deserialize(A, {"key": 0})
assert isinstance(a, A)
assert a.key == 0
assert serialize(a) == {"key": 0}
