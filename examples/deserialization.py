from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import NewType

from apischema import deserialize


@dataclass
class Foo:
    bar: str


MyInt = NewType("MyInt", int)

assert deserialize(Foo, {"bar": "bar"}) == Foo("bar")
assert deserialize(MyInt, 0) == MyInt(0) == 0
assert deserialize(Mapping[str, Collection[Foo]], {"key": [{"bar": "42"}]}) == {
    "key": (Foo("42"),)
}
