from dataclasses import dataclass

from pytest import raises

from apischema import ValidationError, deserialize
from apischema.skip import NotNull


@dataclass
class Foo:
    # NotNull is exactly like Optional for type checkers,
    # it's only interpreted differently by apischema
    bar: NotNull[int] = None


with raises(ValidationError) as err:
    deserialize(Foo, {"bar": None})
assert err.value.errors == [
    {"loc": ["bar"], "err": "expected type integer, found null"}
]
