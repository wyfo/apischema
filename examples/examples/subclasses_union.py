from dataclasses import dataclass

from apischema import deserializer
from apischema.conversions import Conversion, identity
from apischema.json_schema import deserialization_schema


class Base:
    def __init_subclass__(cls, **kwargs):
        # You can use __init_subclass__ to register new subclass automatically
        deserializer(Conversion(identity, source=cls, target=Base))


@dataclass
class Foo(Base):
    foo: int


@dataclass
class Bar(Base):
    bar: str


assert deserialization_schema(Base) == {
    "anyOf": [
        {
            "type": "object",
            "properties": {"foo": {"type": "integer"}},
            "required": ["foo"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"bar": {"type": "string"}},
            "required": ["bar"],
            "additionalProperties": False,
        },
    ],
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
}
