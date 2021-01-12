from typing import Generic, TypeVar

from pytest import raises

from apischema import ValidationError, deserialize, deserializer, serialize, serializer
from apischema.json_schema import deserialization_schema, serialization_schema

T = TypeVar("T")


class Wrapper(Generic[T]):
    def __init__(self, wrapped: T):
        self.wrapped = wrapped

    # serializer methods of generic class are not handled in Python 3.6
    def unwrap(self) -> T:
        return self.wrapped


serializer(Wrapper.unwrap, Wrapper[T], T)
deserializer(Wrapper, T, Wrapper[T])


assert deserialize(Wrapper[list[int]], [0, 1]).wrapped == [0, 1]
with raises(ValidationError):
    deserialize(Wrapper[int], "wrapped")
assert serialize(Wrapper("wrapped")) == "wrapped"
assert (
    deserialization_schema(Wrapper[int])
    == {"$schema": "http://json-schema.org/draft/2019-09/schema#", "type": "integer"}
    == serialization_schema(Wrapper[int])
)
