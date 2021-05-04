from apischema import deserialize, serialize
from apischema.json_schema import deserialization_schema
from apischema.objects import ObjectField, set_object_fields


class Foo:
    def __init__(self, bar):
        self.bar = bar


set_object_fields(Foo, [ObjectField("bar", int)])
# Fields can also be passed in a factory
set_object_fields(Foo, lambda: [ObjectField("bar", int)])

foo = deserialize(Foo, {"bar": 0})
assert isinstance(foo, Foo) and foo.bar == 0
assert serialize(Foo(0)) == {"bar": 0}
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "required": ["bar"],
    "additionalProperties": False,
}
