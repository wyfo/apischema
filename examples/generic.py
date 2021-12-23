from dataclasses import dataclass
from typing import Generic, TypeVar

import pytest

from apischema import ValidationError, deserialize

T = TypeVar("T")


@dataclass
class Box(Generic[T]):
    content: T


assert deserialize(Box[str], {"content": "void"}) == Box("void")
with pytest.raises(ValidationError):
    deserialize(Box[str], {"content": 42})
