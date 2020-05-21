from base64 import b64decode, b64encode
from typing import NewType

from pytest import raises

from apischema import ValidationError, from_data, input_converter
from apischema.conversion import raw_input_converter

input_converter(b64decode, str, bytes)
CheckedBinary = NewType("CheckedBinary", bytes)


def compute_checksum(bytes_: bytes) -> int:
    return sum(bytes_) % (2 ** 32)


@raw_input_converter
def check_binary(binary: bytes, checksum: int) -> CheckedBinary:
    if checksum != compute_checksum(binary):
        raise ValidationError(["invalid checksum"])
    return CheckedBinary(binary)


def test_check_binary():
    binary = b'data!'
    data = {
        "binary":   b64encode(binary).decode(),
        "checksum": compute_checksum(binary),
    }
    assert from_data(CheckedBinary, data) == binary
    with raises(ValidationError) as err:
        from_data(CheckedBinary, {"binary": b64encode(binary).decode(), "checksum": 0})
    assert err.value == ValidationError(["invalid checksum"])
