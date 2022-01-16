from dataclasses import dataclass
from typing import Annotated, Union

import pytest

from apischema import Unsupported, ValidationError, deserialize


@dataclass
class Foo:
    bar: Union[int, Annotated[None, Unsupported]] = None


def test_unsupported_union_member():
    with pytest.raises(ValidationError) as err:
        deserialize(Foo, {"bar": None})
    assert err.value.errors == [
        {"loc": ["bar"], "err": "expected type integer, found null"}
    ]
