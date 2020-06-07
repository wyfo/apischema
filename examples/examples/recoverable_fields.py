from typing import Any, Generic, TypeVar, Union
from typing_extensions import Annotated

from pytest import raises

from apischema import Skip, deserialize, deserializer, serialize, serializer
from apischema.json_schema import deserialization_schema, serialization_schema


class RecoverableRaw(Exception):
    def __init__(self, raw):
        self.raw = raw


deserializer(RecoverableRaw, Any, RecoverableRaw)

T = TypeVar("T")


class Recoverable(Generic[T]):
    def __init__(self, value: T):
        self._value = value

    @property
    def value(self) -> T:
        if isinstance(self._value, RecoverableRaw):
            raise self._value
        return self._value

    @value.setter
    def value(self, value: T):
        self._value = value


deserializer(
    Recoverable,
    Union[T, Annotated[RecoverableRaw, Skip(schema_only=True)]],
    Recoverable[T],
)


@serializer
def serialize_recoverable(recoverable: Recoverable[T]) -> T:
    return recoverable.value


assert deserialize(Recoverable[int], 0).value == 0
with raises(RecoverableRaw) as err:
    assert deserialize(Recoverable[int], "bad").value
assert err.value.raw == "bad"

assert serialize(Recoverable(0)) == 0
with raises(RecoverableRaw) as err:
    assert serialize(Recoverable(RecoverableRaw("bad")))
assert err.value.raw == "bad"

assert (
    deserialization_schema(Recoverable[int])
    == {"$schema": "http://json-schema.org/draft/2019-09/schema#", "type": "integer"}
    == serialization_schema(Recoverable[int])
)
