from typing import TypeVar, cast

import pytest

from apischema import ValidationError, deserialize

T = TypeVar("T")


def coerce(cls: type[T], data) -> T:
    """Only coerce int to bool"""
    if cls is bool and isinstance(data, int):
        return cast(T, bool(data))
    else:
        return data


with pytest.raises(ValidationError):
    deserialize(bool, 0)
with pytest.raises(ValidationError):
    assert deserialize(bool, "ok", coerce=coerce)
assert deserialize(bool, 1, coerce=coerce)
