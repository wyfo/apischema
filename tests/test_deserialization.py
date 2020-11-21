from dataclasses import InitVar, dataclass, field
from typing import Generic, TypeVar

from apischema.deserialization import get_init_merged_alias
from apischema.metadata import init_var, merged


@dataclass
class A:
    a: int
    b: "B" = field(metadata=merged)
    c: "C[int]" = field(metadata=merged)
    d: "D" = field(metadata=merged)
    e: InitVar[int] = field(metadata=init_var(int))
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
    assert set(get_init_merged_alias(A)) == {"a", "g", "h", "i", "e"}
