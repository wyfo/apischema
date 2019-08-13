from dataclasses import dataclass
from typing import Optional

from apischema.null import null_values, set_null_values


@dataclass
class Test:
    a: Optional[int] = None
    b: Optional[int] = None


def test_null():
    test = Test()
    set_null_values(test, "a")
    assert list(null_values(test)) == ["a"]
