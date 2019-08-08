from contextlib import nullcontext
from dataclasses import dataclass
from typing import cast
from unittest.mock import Mock

from pytest import mark, raises

from src.validator import (PartialValidator, Validator, ValidatorMock,
                           validate,
                           validators)


@dataclass
class Test:
    a: int
    b: int

    @validate
    def equal(self):
        if self.a <= self.b:
            yield "a must be greater than b"

    @validate("a")
    def a_gt_10(self, value, name):
        if value <= 10:
            yield f"{name} must be greater than 10"


def test_decorator():
    assert Test.equal.__class__ is Validator
    assert Test.a_gt_10.__class__ is PartialValidator


def test_validators():
    assert validators(Test) == [Test.equal]
    assert validators(Test, PartialValidator) == [Test.a_gt_10]


@mark.parametrize("field, expected", [
    (0, []),
    (-1, ["error"])
])
def test_validator(field, expected):
    @validate
    def validator(self):
        if self.field < 0:
            yield "error"

    obj = Mock()
    obj.field = field
    assert list(validator(obj)) == expected


@mark.parametrize("fields, called", [
    ({"field": 0}, True),
    ({}, False)
])
def test_partial_validator(fields, called):
    @validate("field")
    def validator(_): ...

    assert validator.can_be_called(fields) == called


@dataclass
class TestMock:
    a: int
    b: int

    def test1(self) -> bool:
        return self.a == self.b

    def test2(self, arg: int) -> bool:
        return self.a + self.b == arg


@mark.parametrize("fields, ctx", [
    ({"a": 1, "b": 1}, nullcontext((True, False))),
    ({"a": 1}, raises(AttributeError)),
])
def test_mock(fields, ctx):
    mock = cast(TestMock, ValidatorMock(fields, TestMock))
    for f in fields:
        assert fields[f] == getattr(mock, f)
    with ctx as res:
        assert (mock.test1(), mock.test2(1)) == res
