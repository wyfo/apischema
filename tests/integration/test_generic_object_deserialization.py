from typing import Collection, TypeVar

import pytest

from apischema import ValidationError, deserialize
from apischema.objects import object_deserialization

T = TypeVar("T")


def repeat(item: T, number: int) -> Collection[T]:
    return [item] * number


repeat_conv = object_deserialization(repeat)


def test_generic_object_deserialization():
    assert deserialize(
        Collection[int], {"item": 0, "number": 3}, conversion=repeat_conv
    ) == [0, 0, 0]
    with pytest.raises(ValidationError):
        deserialize(Collection[str], {"item": 0, "number": 3}, conversion=repeat_conv)
