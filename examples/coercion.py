from pytest import raises

from apischema import ValidationError, deserialize

with raises(ValidationError):
    deserialize(bool, "ok")
assert deserialize(bool, "ok", coercion=True)
