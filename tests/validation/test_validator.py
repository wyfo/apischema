from dataclasses import dataclass
from typing import Callable, Type

from pytest import raises

from apischema import ValidationError, validator
from apischema.validation.mock import NonTrivialDependency, ValidatorMock
from apischema.validation.validators import Validator, get_validators, validate


@dataclass
class Data:
    a: int
    b: int
    c: int = 0

    @validator
    def a_gt_10(self):
        if self.a <= 10:
            yield "error"

    @validator
    def a_lt_100(self):
        if self.a >= 100:
            raise ValidationError("error2")

    @validator
    def non_trivial(self):
        non_trivial(self)


def non_trivial(data: Data):
    return data.c == data.b


def get_validators_by_method(cls: Type, method: Callable) -> Validator:
    return next(val for val in get_validators(cls) if val.func == method)


def test_get_validators():
    assert get_validators(Data) == [
        get_validators_by_method(Data, method)
        for method in (Data.a_gt_10, Data.a_lt_100, Data.non_trivial)
    ]


def test_validator_descriptor():
    # Class field is descriptor
    validator = get_validators_by_method(Data, Data.a_gt_10)
    assert validator.dependencies == {"a"}
    # Can be called from class and instance
    with raises(ValidationError):
        assert Data(200, 0).a_lt_100()
    with raises(ValidationError):
        assert Data.a_lt_100(Data(200, 0))


def test_validate():
    validate(Data(42, 0))
    with raises(ValidationError) as err:
        validate(Data(0, 0))
    assert err.value.errors == [{"loc": [], "err": "error"}]
    with raises(ValidationError) as err:
        validate(Data(200, 0))
    assert err.value.errors == [{"loc": [], "err": "error2"}]


def test_non_trivial():
    with raises(NonTrivialDependency) as err:
        validate(ValidatorMock(Data, {"a": 42}), get_validators(Data))
    # err.value.attr != "c" because `c` has a default value
    assert err.value.attr == "b"
    assert err.value.validator.func == Data.non_trivial
