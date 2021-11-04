import sys
from dataclasses import dataclass

from pytest import raises

from apischema import ValidationError, deserialization_method, deserialize, validator


def validate_checksum(b: bytes):
    if b and sum(b[:-1]) % 255 != int(b[-1]):
        raise ValueError("Invalid checksum")


valid_bytes = b"toto" + (sum(b"toto") % 255).to_bytes(1, byteorder=sys.byteorder)
invalid_bytes = b"toto" + (sum(b"toto") % 255 + 42).to_bytes(1, byteorder=sys.byteorder)

checked_bytes_method = deserialization_method(
    bytes, allowed_types={bytes}, validators=[validate_checksum]
)


def test_allowed_types_upper_validators():
    validate_checksum(valid_bytes)
    with raises(ValueError):
        validate_checksum(invalid_bytes)
    assert checked_bytes_method(valid_bytes) is valid_bytes
    with raises(ValidationError):
        checked_bytes_method(invalid_bytes)


@dataclass
class MyClass:
    field: int

    @validator
    def field_is_not_zero(self):
        if self.field == 0:
            raise ValueError("ZERO!")


def test_allowed_types_type_validators():
    obj = MyClass(0)
    assert deserialize(MyClass, obj, allowed_types={MyClass}) is obj
    with raises(ValidationError):
        deserialize(MyClass, {"field": 0}, allowed_types={MyClass})
