import sys
from typing import Generic, TypeVar

from pytest import raises

from apischema import ValidationError, deserialize, deserializer, serialize, serializer
from apischema.json_schema import deserialization_schema, serialization_schema

T = TypeVar("T")


class Wrapper(Generic[T]):
    def __init__(self, wrapped: T):
        self.wrapped = wrapped

    if sys.version_info >= (3, 7):
        # Methods of generic classes are not handled before 3.7
        @serializer
        def unwrap(self) -> T:
            return self.wrapped

    else:

        def unwrap(self) -> T:
            return self.wrapped


if sys.version_info <= (3, 7):
    serializer(Wrapper.unwrap, Wrapper[T])

U = TypeVar("U")
deserializer(Wrapper, U, Wrapper[U])
# Roughly equivalent to:
# @deserializer
# def wrap(obj: U) -> Wrapper[U]:
#     return Wrapper(obj)


assert deserialize(Wrapper[list[int]], [0, 1]).wrapped == [0, 1]
with raises(ValidationError):
    deserialize(Wrapper[int], "wrapped")
assert serialize(Wrapper("wrapped")) == "wrapped"
assert (
    deserialization_schema(Wrapper[int])
    == {"$schema": "http://json-schema.org/draft/2019-09/schema#", "type": "integer"}
    == serialization_schema(Wrapper[int])
)
