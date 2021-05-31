from apischema import deserialize, serialize
from apischema.objects import ObjectField, set_object_fields


class Foo:
    def __init__(self, bar: int):
        self.bar = bar


set_object_fields(Foo, lambda: [ObjectField("bar", int, required=True)])

foo = deserialize(Foo, {"bar": 0})
assert type(foo) == Foo and foo.bar == 0
assert serialize(Foo, Foo(0)) == {"bar": 0}
