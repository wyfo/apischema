from dataclasses import dataclass, field
from enum import Enum

from pytest import raises

from apischema import ValidationError, deserialize, serialize, validator
from apischema.fields import fields


class Parity(Enum):
    EVEN = "even"
    ODD = "odd"


@dataclass
class NumberWithParity:
    parity: Parity
    number: int = field()  # field must be assign, even with empty `field()`

    @validator(number)
    def check_parity(self):
        if (self.parity == Parity.EVEN) != (self.number % 2 == 0):
            yield "number doesn't respect parity"

    # using field argument adds automatically discard argument
    # and prefix all error paths with the field
    @validator(discard=number)
    def check_parity_equivalent(self):
        if (self.parity == Parity.EVEN) != (self.number % 2 == 0):
            yield fields(self).number, "number doesn't respect parity"


with raises(ValidationError) as err:
    deserialize(NumberWithParity, {"parity": "even", "number": 1})
assert serialize(err.value) == [
    {"loc": ["number"], "err": ["number doesn't respect parity"]}
]
