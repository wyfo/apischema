from apischema import deserialize, serialize
from apischema.json_schema import deserialization_schema
from apischema.objects import ObjectField, object_conversion


class Foo:
    def __init__(self, bar):
        self.bar = bar


foo_deserialization, foo_serialization = object_conversion(
    Foo, [ObjectField(name="bar", type=int, required=True)]
)

foo = deserialize(Foo, {"bar": 0}, conversions=foo_deserialization)
assert isinstance(foo, Foo) and foo.bar == 0
assert serialize(Foo(0), conversions=foo_serialization) == {"bar": 0}
assert deserialization_schema(Foo, conversions=foo_deserialization) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "required": ["bar"],
    "additionalProperties": False,
}
