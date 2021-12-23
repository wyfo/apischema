from dataclasses import dataclass

import pytest

from apischema import ValidationError, deserialize


@dataclass
class Foo:
    bar: str


data = {"bar": "bar", "other": 42}
with pytest.raises(ValidationError):
    deserialize(Foo, data)
assert deserialize(Foo, data, additional_properties=True) == Foo("bar")
