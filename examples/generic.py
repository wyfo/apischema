from dataclasses import dataclass
from typing import Generic, TypeVar

from pytest import raises

from apischema import ValidationError, deserialize

T = TypeVar("T")


@dataclass
class Box(Generic[T]):
    content: T


assert deserialize(Box[str], {"content": "void"}) == Box("void")
with raises(ValidationError):
    deserialize(Box[str], {"content": 42})
