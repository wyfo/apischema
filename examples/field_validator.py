from dataclasses import dataclass, field

from pytest import raises

from apischema import ValidationError, deserialize
from apischema.metadata import validators


def check_no_duplicate_digits(n: int):
    if len(str(n)) != len(set(str(n))):
        raise ValidationError("number has duplicate digits")


@dataclass
class Foo:
    bar: str = field(metadata=validators(check_no_duplicate_digits))


with raises(ValidationError) as err:
    deserialize(Foo, {"bar": "11"})
assert err.value.errors == [{"loc": ["bar"], "msg": "number has duplicate digits"}]
