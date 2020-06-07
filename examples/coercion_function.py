from typing import Type, TypeVar, cast

from pytest import raises

from apischema import ValidationError, deserialize

T = TypeVar("T")


def coerce(cls: Type[T], data) -> T:
    """Only coerce int to bool"""
    if cls is bool and isinstance(data, int):
        return cast(T, bool(data))
    else:
        return data


with raises(ValidationError):
    deserialize(bool, 0)
with raises(ValidationError):
    assert deserialize(bool, "ok", coercion=coerce)
assert deserialize(bool, 1, coercion=coerce)
