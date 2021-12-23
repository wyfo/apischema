import pytest

from apischema import ValidationError, deserialize

with pytest.raises(ValidationError):
    deserialize(bool, "ok")
assert deserialize(bool, "ok", coerce=True)
