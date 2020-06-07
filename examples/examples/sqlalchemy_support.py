from dataclasses import field, make_dataclass
from inspect import getmembers

from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import as_declarative

from apischema import deserialize, deserializer, serialize, serializer
from apischema.fields import fields_set, with_fields_set


@as_declarative()
class Base:
    def __init_subclass__(cls):
        columns = getmembers(cls, lambda m: isinstance(m, Column))
        if not columns:
            return
        fields = [
            (col.name or f, col.type.python_type, field(default=None))
            for f, col in columns
        ]
        dataclass = make_dataclass(cls.__name__, fields)
        with_fields_set(dataclass)

        def from_data(data):
            return cls(**{f: getattr(data, f) for f in fields_set(data)})

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
