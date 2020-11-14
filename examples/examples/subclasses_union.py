from dataclasses import dataclass

from apischema import deserializer
from apischema.conversions import identity
from apischema.json_schema import deserialization_schema


class Base:
    pass


@dataclass
class Foo(Base):
    foo: int


@dataclass
class Bar(Base):
    bar: str


@deserializer
def from_foo(foo: Foo) -> Base:
    return foo


deserializer(identity, Bar, Base)
# Roughly equivalent to
# @deserializer
# def from_bar(bar: Bar) -> Base:
#     return bar
# but identity is optimized by Apischema

# You can even add deserializers which are not subclass
@deserializer
def from_list_of_int(ints: list[int]) -> Base:
    return Base()


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
        {"type": "array", "items": {"type": "integer"}},
    ],
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
}
