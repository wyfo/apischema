from dataclasses import dataclass
from typing import Generic, TypeVar

from apischema import serialized
from apischema.json_schema import serialization_schema

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class Foo(Generic[T]):
    @serialized
    def bar(self) -> T: ...


@serialized
def baz(foo: Foo[U]) -> U: ...


@dataclass
class FooInt(Foo[int]): ...


assert (
    serialization_schema(Foo[int])
    == serialization_schema(FooInt)
    == {
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
        "type": "object",
        "properties": {"bar": {"type": "integer"}, "baz": {"type": "integer"}},
        "required": ["bar", "baz"],
        "additionalProperties": False,
    }
)
