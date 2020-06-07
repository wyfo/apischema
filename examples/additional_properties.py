from dataclasses import dataclass

from pytest import raises

from apischema import ValidationError, deserialize


@dataclass
class Foo:
    bar: str


data = {"bar": "bar", "other": 42}
with raises(ValidationError):
    deserialize(Foo, data)
assert deserialize(Foo, data, additional_properties=True) == Foo("bar")
