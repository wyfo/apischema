from dataclasses import dataclass

from pytest import raises

from apischema import NotNull, ValidationError, deserialize, serialize


@dataclass
class Foo:
    # NotNull is exactly like Optional for type checkers,
    # it's only considered differently by Apischema
    bar: NotNull[int] = None


with raises(ValidationError) as err:
    deserialize(Foo, {"bar": None})
assert serialize(err.value) == [
    {"loc": ["bar"], "err": ["expected type integer, found null"]}
]
