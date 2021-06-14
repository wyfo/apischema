from dataclasses import dataclass
from typing import Annotated, Union

from pytest import raises

from apischema import ValidationError, deserialize
from apischema.skip import Skip


@dataclass
class Foo:
    bar: Union[int, Annotated[None, Skip]] = None


with raises(ValidationError) as err:
    deserialize(Foo, {"bar": None})
assert err.value.errors == [
    {"loc": ["bar"], "msg": "expected type integer, found null"}
]
