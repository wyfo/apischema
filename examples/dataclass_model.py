from dataclasses import dataclass

from apischema import deserialize, serialize
from apischema.conversions import dataclass_model
from apischema.json_schema import deserialization_schema


class Foo:
    def __init__(self, bar):
        self.bar = bar


@dataclass
class FooModel:
    bar: int


deserialization_conversion, serialization_conversion = dataclass_model(Foo, FooModel)
# You can also register these conversions with apischema.deserializer/apischema.serializer

foo = deserialize(Foo, {"bar": 0}, conversions=deserialization_conversion)
assert isinstance(foo, Foo) and foo.bar == 0
assert serialize(Foo(0), conversions=serialization_conversion) == {"bar": 0}
assert deserialization_schema(Foo, conversions=deserialization_conversion) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "required": ["bar"],
    "additionalProperties": False,
}
