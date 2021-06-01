from dataclasses import dataclass

from apischema import deserialization_method, serialization_method


@dataclass
class Foo:
    bar: int


deserialize_foo = deserialization_method(Foo)
serialize_foo = serialization_method(Foo)

assert deserialize_foo({"bar": 0}) == Foo(0)
assert serialize_foo(Foo(0)) == {"bar": 0}
