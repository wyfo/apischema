from dataclasses import dataclass
from typing import Generic, TypeVar

from apischema import serialized
from apischema.json_schema import serialization_schema

T = TypeVar("T")


@dataclass
class Foo(Generic[T]):
    # serialized decorator for methods of generic class is not supported in Python 3.6
    def bar(self) -> T:
        ...


serialized(Foo.bar)


@dataclass
class FooInt(Foo[int]):
    ...


assert (
    serialization_schema(Foo[int])
    == serialization_schema(FooInt)
    == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "object",
        "properties": {"bar": {"type": "integer"}},
        "required": ["bar"],
        "additionalProperties": False,
    }
)
