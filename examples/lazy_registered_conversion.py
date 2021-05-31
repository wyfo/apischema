from dataclasses import dataclass

from apischema import deserialize, deserializer, serialize, serializer
from apischema.conversions import Conversion


@dataclass
class Foo:
    bar: int


deserializer(
    lazy=lambda: Conversion(lambda bar: Foo(bar), source=int, target=Foo), target=Foo
)
serializer(
    lazy=lambda: Conversion(lambda foo: foo.bar, source=Foo, target=int), source=Foo
)

assert deserialize(Foo, 0) == Foo(0)
assert serialize(Foo, Foo(0)) == 0
