from dataclasses import dataclass

from apischema import serialize


@dataclass
class Foo:
    bar: int = 0
    baz: str | None = None


assert serialize(Foo, Foo(), exclude_defaults=True) == {}
assert serialize(Foo, Foo(), exclude_none=True) == {"bar": 0}
