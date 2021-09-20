from typing import Generic, TypeVar

from pytest import raises

from apischema import ValidationError, deserialize, serialize
from apischema.conversions import deserializer, serializer
from apischema.json_schema import deserialization_schema, serialization_schema

T = TypeVar("T")


class Wrapper(Generic[T]):
    def __init__(self, wrapped: T):
        self.wrapped = wrapped

    @serializer
    def unwrap(self) -> T:
        return self.wrapped


# Wrapper constructor can be used as a function too (so deserializer could work as decorator)
deserializer(Wrapper)


assert deserialize(Wrapper[list[int]], [0, 1]).wrapped == [0, 1]
with raises(ValidationError):
    deserialize(Wrapper[int], "wrapped")
assert serialize(Wrapper[str], Wrapper("wrapped")) == "wrapped"
assert (
    deserialization_schema(Wrapper[int])
    == {"$schema": "http://json-schema.org/draft/2020-12/schema#", "type": "integer"}
    == serialization_schema(Wrapper[int])
)
