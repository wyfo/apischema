from dataclasses import dataclass, field

import pytest

from apischema import ValidationError, deserialize, validator
from apischema.objects import AliasedStr, get_alias


@dataclass
class A:
    a: int = field()

    @validator(a)
    def validate_a(self):
        yield (get_alias(self).a, "b", 0, AliasedStr("c")), f"error {self.a}"


def test_validator_aliasing():
    with pytest.raises(ValidationError) as err:
        deserialize(A, {"A": 42}, aliaser=str.upper)
    assert err.value.errors == [{"loc": ["A", "A", "b", 0, "C"], "err": "error 42"}]
