from dataclasses import dataclass
from typing import Annotated, Union  # type: ignore

from pytest import raises

from apischema import Unsupported, ValidationError, deserialize


@dataclass
class Foo:
    bar: Union[int, Annotated[None, Unsupported]] = None


def test_unsupported_union_member():
    with raises(ValidationError) as err:
        deserialize(Foo, {"bar": None})
    assert err.value.errors == [
        {"loc": ["bar"], "err": "expected type integer, found null"}
    ]
