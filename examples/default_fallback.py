from dataclasses import dataclass, field

from pytest import raises

from apischema import ValidationError, deserialize
from apischema.metadata import default_fallback


@dataclass
class Foo:
    bar: str = "bar"
    baz: str = field(default="baz", metadata=default_fallback)


with raises(ValidationError):
    deserialize(Foo, {"bar": 0})
assert deserialize(Foo, {"bar": 0}, default_fallback=True) == Foo()

assert deserialize(Foo, {"baz": 0}) == Foo()
