import json
from dataclasses import dataclass

from apischema import order, serialize


@order(["baz", "bar"])
@dataclass
class Foo:
    bar: int
    baz: int


assert json.dumps(serialize(Foo, Foo(0, 0))) == '{"baz": 0, "bar": 0}'
