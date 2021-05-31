from dataclasses import dataclass

from apischema import deserialize, serialize


@dataclass
class Foo:
    field: int


@dataclass
class Bar(Foo):
    other: str


def foo_to_int(foo: Foo) -> int:
    return foo.field


def bar_from_int(i: int) -> Bar:
    return Bar(i, str(i))


assert serialize(Bar, Bar(0, ""), conversions=foo_to_int) == 0
assert deserialize(Foo, 0, conversions=bar_from_int) == Bar(0, "0")
