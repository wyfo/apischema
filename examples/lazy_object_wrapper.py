from apischema import deserialize, serialize
from apischema.objects import ObjectField, register_object_wrapper


class Foo:
    def __init__(self, bar: int):
        self.bar = bar


register_object_wrapper(Foo, lambda: [ObjectField("bar", int, required=True)])

foo = deserialize(Foo, {"bar": 0})
assert type(foo) == Foo and foo.bar == 0
assert serialize(Foo(0)) == {"bar": 0}
