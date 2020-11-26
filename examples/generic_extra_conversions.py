from dataclasses import dataclass
from typing import Generic, TypeVar

from apischema import serialize
from apischema.conversions import extra_serializer

T = TypeVar("T")


@dataclass
class Foo(Generic[T]):
    bar: T


@extra_serializer
def to_bar(foo: Foo[T]) -> T:
    return foo.bar


assert serialize(Foo(0)) == {"bar": 0}
# {Foo: ([T], T)} means a conversions Foo[T] -> T
assert serialize(Foo(0), conversions={Foo: ([T], T)}) == 0
# Conversion is not tied to a specific TypeVar
U = TypeVar("U")
assert serialize(Foo(0), conversions={Foo: ([U], U)}) == 0
