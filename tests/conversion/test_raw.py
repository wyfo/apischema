from typing import Dict

from pytest import mark, raises

from apischema import ValidationError, deserialize, deserializer
from apischema.conversion.raw import to_raw_deserializer


def untyped_return():
    pass


def untyped_param(a) -> str:
    pass


def vararg(*args) -> str:
    pass


@mark.parametrize("func", [untyped_return, untyped_param, vararg])
def test_raw_errors(func):
    with raises(TypeError):
        to_raw_deserializer(func)


class SuffixedVersion(str):
    pass


def sfx_version(version: int, suffix: str = "") -> SuffixedVersion:
    return SuffixedVersion(f"{version}{suffix}")


def test_raw():
    deserializer(to_raw_deserializer(sfx_version))
    assert deserialize(SuffixedVersion, {"version": 42}) == "42"
    assert deserialize(SuffixedVersion, {"version": 42, "suffix": "ok"}) == "42ok"
    deserializer(to_raw_deserializer(sfx_version))
    with raises(ValidationError):
        deserialize(SuffixedVersion, {"version": "42"})


class IntDict(Dict[str, int]):
    pass


def int_dict(mandatory: int, **kwargs: int) -> IntDict:
    return IntDict(kwargs)


def test_raw_with_kwargs():
    deserializer(to_raw_deserializer(int_dict))
    assert deserialize(IntDict, {"mandatory": 42, "a": 0}) == IntDict({"a": 0})
    with raises(ValidationError):
        deserialize(IntDict, {"mandatory": 42, "a": "0"})
    with raises(ValidationError):
        deserialize(IntDict, {"a": 0})
