from dataclasses import Field, dataclass, field
from operator import not_
from typing import cast

from pytest import raises

from apischema import ValidationError, validator
from apischema.fields import fields
from apischema.validation.mock import NonTrivialDependency, ValidatorMock
from apischema.validation.validator import Validator, get_validators, validate, validators


@dataclass
class Data:
    a: int
    b: int
    c: int = 0
    with_validator: bool = field(default=False, metadata=validators(not_))

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


validator_field = cast(Field, fields(Data).with_validator)


def non_trivial(data: Data):
    return data.c == data.b


def test_get_validators():
    assert get_validators(Data) == (Data.a_gt_10, Data.a_lt_100, Data.non_trivial)


def test_validator_descriptor():
    # Class field is descriptor
    val: Validator = Data.a_gt_10
    assert val.dependencies == {"a"}
    # Can be called from class and instance
    with raises(ValueError):
        assert Data(200, 0).a_lt_100()
    with raises(ValueError):
        assert Data.a_lt_100(Data(200, 0))


def test_validate():
    validate(Data(42, 0))
    with raises(ValidationError) as err:
        validate(Data(0, 0))
    assert err.value == ValidationError(["error"])
    with raises(ValidationError) as err:
        validate(Data(200, 0))
    assert err.value == ValidationError(["error2"])


def test_non_trivial():
    with raises(NonTrivialDependency) as err:
        validate(ValidatorMock(Data, {"a": 42}))
    # err.value.attr != "c" because `c` has a default value
    assert err.value.attr == "b"
    assert err.value.validator == Data.non_trivial
