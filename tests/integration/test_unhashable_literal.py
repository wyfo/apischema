import pytest

from apischema import ValidationError, deserialize
from apischema.typing import Literal


def test_unhashable_literal():
    with pytest.raises(ValidationError):
        deserialize(Literal[0], {})
