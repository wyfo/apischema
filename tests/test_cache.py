from dataclasses import InitVar, dataclass, field
from typing import Generic, TypeVar

from apischema.dataclasses.cache import _deserialization_merged_aliases
from apischema.metadata import merged


@dataclass
class A:
    a: int
    b: "B" = field(metadata=merged)
    c: "C[int]" = field(metadata=merged)
    d: "D" = field(metadata=merged)
    e: InitVar[int]
    f: int = field(init=False)


@dataclass
class B:
    g: int


T = TypeVar("T")


@dataclass
class C(Generic[T]):
    h: T


@dataclass
class D(Generic[T]):
    i: T


def test_merged_aliases():
    assert _deserialization_merged_aliases(A) == {"a", "g", "h", "i", "e"}
