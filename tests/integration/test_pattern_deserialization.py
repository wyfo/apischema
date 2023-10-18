import re

import pytest

from apischema import ValidationError, deserialize


def test_valid_pattern():
    pattern = deserialize(re.Pattern, "(a|b)")
    assert isinstance(pattern, re.Pattern)
    assert pattern.pattern == "(a|b)"


def test_invalid_pattern():
    with pytest.raises(ValidationError):
        deserialize(re.Pattern, "(a")
