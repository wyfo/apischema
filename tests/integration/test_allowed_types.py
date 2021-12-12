import sys
from dataclasses import dataclass

from pytest import raises

from apischema import ValidationError, deserialization_method, deserialize, validator


def validate_checksum(b: bytes):
    if b and sum(b[:-1]) % 255 != int(b[-1]):
        raise ValidationError("Invalid checksum")


valid_bytes = b"toto" + (sum(b"toto") % 255).to_bytes(1, byteorder=sys.byteorder)
invalid_bytes = b"toto" + (sum(b"toto") % 255 + 42).to_bytes(1, byteorder=sys.byteorder)


def test_allowed_types_run_upper_validators():
    method = deserialization_method(
        bytes, allowed_types={bytes}, validators=[validate_checksum]
    )
    assert method(valid_bytes) is valid_bytes
    with raises(ValidationError):
        method(invalid_bytes)


@dataclass
class MyClass:
    field: int

    @validator
    def field_is_not_zero(self):
        if self.field == 0:
            raise ValidationError("ZERO!")


def test_allowed_types_doesnt_run_type_validators():
    obj = MyClass(0)
    method = deserialization_method(MyClass, allowed_types={MyClass})
    assert method(obj) is obj
    with raises(ValidationError):
        method({"fields": 0})
        deserialize(MyClass, {"field": 0}, allowed_types={MyClass})
