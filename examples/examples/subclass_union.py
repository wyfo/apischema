from dataclasses import dataclass
from typing import Any, Union

from apischema import deserialize, deserializer, identity, serializer
from apischema.conversions import Conversion
from apischema.json_schema import deserialization_schema, serialization_schema


class Base:
    _union: Any = None

    # You can use __init_subclass__ to register new subclass automatically
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Deserializers stack directly as a Union
        deserializer(Conversion(identity, source=cls, target=Base))
        # Only Base serializer must be registered (and updated for each subclass) as
        # a Union, and not be inherited
        Base._union = cls if Base._union is None else Union[Base._union, cls]
        serializer(
            Conversion(identity, source=Base, target=Base._union, inherited=False)
        )


@dataclass
class Foo(Base):
    foo: int


@dataclass
class Bar(Base):
    bar: str


assert (
    deserialization_schema(Base)
    == serialization_schema(Base)
    == {
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
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
    }
)
assert deserialize(Base, {"foo": 0}) == Foo(0)
