from dataclasses import dataclass

import pytest

from apischema import ValidationError, deserialize
from apischema.skip import NotNull


@dataclass
class Foo:
    # NotNull is exactly like Optional for type checkers,
    # it's only interpreted differently by apischema
    bar: NotNull[int] = None


with pytest.raises(ValidationError) as err:
    deserialize(Foo, {"bar": None})
assert err.value.errors == [
    {"loc": ["bar"], "err": "expected type integer, found null"}
]
