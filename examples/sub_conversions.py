from dataclasses import dataclass
from typing import Generic, TypeVar

from apischema.conversions import Conversion
from apischema.json_schema import serialization_schema

T = TypeVar("T")


class Query(Generic[T]): ...


def query_to_list(q: Query[T]) -> list[T]: ...


def query_to_scalar(q: Query[T]) -> T | None: ...


@dataclass
class FooModel:
    bar: int


class Foo:
    def serialize(self) -> FooModel: ...


assert serialization_schema(
    Query[Foo], conversion=Conversion(query_to_list, sub_conversion=Foo.serialize)
) == {
    # We get an array of Foo
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"bar": {"type": "integer"}},
        "required": ["bar"],
        "additionalProperties": False,
    },
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
}
