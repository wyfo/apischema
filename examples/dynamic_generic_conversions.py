from dataclasses import dataclass
from typing import Generic, TypeVar

from apischema import serialize

T = TypeVar("T")


@dataclass
class Foo(Generic[T]):
    bar: T


U = TypeVar("U")


def to_bar(foo: Foo[U]) -> U:
    return foo.bar


assert serialize(Foo(0)) == {"bar": 0}
assert serialize(Foo(0), conversions=to_bar) == 0
