from dataclasses import dataclass, field
from typing import Generic, TypeVar

from apischema import deserialize
from apischema.metadata import merged

T = TypeVar("T")


@dataclass
class A(Generic[T]):
    pass


@dataclass
class B(Generic[T]):
    a1: A = field(metadata=merged)
    a2: A[T] = field(metadata=merged)
    a3: A[int] = field(metadata=merged)


def test_merged_generic_dataclass():
    deserialize(B, {})  # it works
