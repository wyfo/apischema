from dataclasses import dataclass, field

import pytest

from apischema import ValidationError, deserialize
from apischema.metadata import validators


def check_no_duplicate_digits(n: int):
    if len(str(n)) != len(set(str(n))):
        raise ValidationError("number has duplicate digits")


@dataclass
class Foo:
    bar: str = field(metadata=validators(check_no_duplicate_digits))


with pytest.raises(ValidationError) as err:
    deserialize(Foo, {"bar": "11"})
assert err.value.errors == [{"loc": ["bar"], "err": "number has duplicate digits"}]
