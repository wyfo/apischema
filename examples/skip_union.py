from dataclasses import dataclass
from typing import Annotated, Union

from pytest import raises

from apischema import Skip, ValidationError, deserialize, serialize


@dataclass
class Foo:
    bar: Union[int, Annotated[None, Skip]] = None


with raises(ValidationError) as err:
    deserialize(Foo, {"bar": None})
assert serialize(err.value) == [
    {"loc": ["bar"], "err": ["expected type integer, found null"]}
]
