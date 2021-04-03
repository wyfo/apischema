from apischema import deserialize, serialize
from apischema.json_schema import deserialization_schema
from apischema.objects import ObjectField, register_object_wrapper


class Foo:
    def __init__(self, bar):
        self.bar = bar


register_object_wrapper(Foo, [ObjectField("bar", int, True)])

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
