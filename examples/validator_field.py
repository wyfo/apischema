from dataclasses import dataclass, field
from enum import Enum

from pytest import raises

from apischema import ValidationError, deserialize, validator
from apischema.objects import get_alias, get_field


class Parity(Enum):
    EVEN = "even"
    ODD = "odd"


@dataclass
class NumberWithParity:
    parity: Parity
    number: int = field()

    @validator(number)
    def check_parity(self):
        if (self.parity == Parity.EVEN) != (self.number % 2 == 0):
            yield "number doesn't respect parity"

    # A field validator is equivalent to a discard argument and all error paths prefixed
    # with the field alias
    @validator(discard=number)
    def check_parity_equivalent(self):
        if (self.parity == Parity.EVEN) != (self.number % 2 == 0):
            yield get_alias(self).number, "number doesn't respect parity"


@validator(get_field(NumberWithParity).number)
def check_parity_other_equivalent(number2: NumberWithParity):
    if (number2.parity == Parity.EVEN) != (number2.number % 2 == 0):
        yield "number doesn't respect parity"


with raises(ValidationError) as err:
    deserialize(NumberWithParity, {"parity": "even", "number": 1})
assert err.value.errors == [{"loc": ["number"], "msg": "number doesn't respect parity"}]
