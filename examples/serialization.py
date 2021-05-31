from dataclasses import dataclass
from typing import Any

from apischema import serialize


@dataclass
class Foo:
    bar: str


assert serialize(Foo, Foo("baz")) == {"bar": "baz"}
assert serialize(tuple[int, int], (0, 1)) == [0, 1]
assert (
    serialize(Any, {"key": ("value", 42)})
    == serialize({"key": ("value", 42)})
    == {"key": ["value", 42]}
)
assert serialize(Foo("baz")) == {"bar": "baz"}
