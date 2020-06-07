from dataclasses import dataclass

from apischema import serialize


@dataclass
class Foo:
    bar: str


assert serialize(Foo("bar")) == {"bar": "bar"}
assert serialize((0, 1)) == [0, 1]
assert serialize({"key": ("value", 42)}) == {"key": ["value", 42]}
