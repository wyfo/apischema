from dataclasses import dataclass
from typing import Sequence, cast

from pytest import fixture, raises

from apischema import ValidationError, validator
from apischema.validation.mock import NonTrivialDependency, ValidatorMock
from apischema.validation.validator import Validator, get_validators, validate


@dataclass
class Data:
    a: int
    other: str = ""

    @validator
    def a_gt_10(self):
        if self.a <= 10:
            yield "error"

    @validator
    def a_lt_100(self):
        if self.a >= 100:
            raise ValueError("error2")

    @validator
    def non_trivial(self):
        non_trivial(self)


def non_trivial(data: Data):
    return data.other


@fixture
def validators() -> Sequence[Validator]:
    return get_validators(Data)


def test_get_validators(validators):
    assert validators == (Data.a_gt_10, Data.a_lt_100, Data.non_trivial)


def test_validator_descriptor():
    # Class field is descriptor
    val = cast(Validator, Data.a_gt_10)
    assert val.dependencies == {"a"}
    assert val.can_be_called({"a"})
    assert not val.can_be_called(set())
    # Can be called from class and instance
    with raises(ValueError):
        assert Data(200).a_lt_100()
    with raises(ValueError):
        assert Data.a_lt_100(Data(200))


def test_validate(validators):
    validate(Data(42), validators)
    with raises(ValidationError) as err:
        validate(Data(0), validators)
    assert err.value == ValidationError(["error"])
    with raises(ValidationError) as err:
        validate(Data(200), validators)
    assert err.value == ValidationError(["[ValueError]error2"])


def test_non_trivial(validators):
    with raises(NonTrivialDependency) as err:
        validate(ValidatorMock(Data, {"a": 42}, {}), validators)
    assert err.value.attr == "other"
    assert err.value.validator == Data.non_trivial
