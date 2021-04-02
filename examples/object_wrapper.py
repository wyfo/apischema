from apischema import deserialize, serialize
from apischema.objects import ObjectField, object_wrapper


class Foo:
    def __init__(self, bar):
        self.bar = bar


FooWrapper = object_wrapper(Foo, [ObjectField("bar", int, True)])

foo = deserialize(Foo, {"bar": 0}, conversions=FooWrapper.deserialization)
assert isinstance(foo, Foo) and foo.bar == 0
assert serialize(Foo(0), conversions=FooWrapper.serialization) == {"bar": 0}
# assert deserialization_schema(Foo, conversions=serialization) == {
#     "$schema": "http://json-schema.org/draft/2019-09/schema#",
#     "type": "object",
#     "properties": {"bar": {"type": "integer"}},
#     "required": ["bar"],
#     "additionalProperties": False,
# }

# register_object_wrapper(Foo, [ObjectField("bar", int, True)])
# is equivalent to
# FooWrapper = object_wrapper(Foo, [ObjectField("bar", int, True)])
# deserializer(FooWrapper.deserialization)
# serializer(FooWrapper.serialization)
