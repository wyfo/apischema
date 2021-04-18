from typing import Any, Dict, Generic, TypeVar, Union

from pytest import raises

from apischema import deserialize, deserializer, schema, serialize, serializer
from apischema.json_schema import deserialization_schema, serialization_schema


# Add a dummy placeholder comment in order to not have an empty schema
# (because Union member with empty schema would "contaminate" whole Union schema)
@schema(extra={"$comment": "recoverable"})
class RecoverableRaw(Exception):
    def __init__(self, raw: Any):
        self.raw = raw


deserializer(RecoverableRaw)

T = TypeVar("T")


def remove_recoverable_schema(json_schema: Dict[str, Any]):
    if "anyOf" in json_schema:  # deserialization schema
        value_schema, recoverable_comment = json_schema.pop("anyOf")
        assert recoverable_comment == {"$comment": "recoverable"}
        json_schema.update(value_schema)


@schema(extra=remove_recoverable_schema)
class Recoverable(Generic[T]):
    def __init__(self, value: Union[T, RecoverableRaw]):
        self._value = value

    @property
    def value(self) -> T:
        if isinstance(self._value, RecoverableRaw):
            raise self._value
        return self._value

    @value.setter
    def value(self, value: T):
        self._value = value


deserializer(Recoverable)
serializer(Recoverable.value)

assert deserialize(Recoverable[int], 0).value == 0
with raises(RecoverableRaw) as err:
    _ = deserialize(Recoverable[int], "bad").value
assert err.value.raw == "bad"

assert serialize(Recoverable(0)) == 0
with raises(RecoverableRaw) as err:
    serialize(Recoverable(RecoverableRaw("bad")))
assert err.value.raw == "bad"

assert (
    deserialization_schema(Recoverable[int])
    == serialization_schema(Recoverable[int])
    == {"$schema": "http://json-schema.org/draft/2019-09/schema#", "type": "integer"}
)
