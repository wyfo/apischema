from dataclasses import InitVar, dataclass, field
from typing import Generic, TypeVar

from pytest import raises

from apischema.deserialization import get_deserialization_merged_aliases
from apischema.metadata import init_var, merged
from apischema.objects import object_fields


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


@dataclass
class Data:
    field: A = field(metadata=merged)


def test_merged_aliases():
    assert set(
        get_deserialization_merged_aliases(Data, object_fields(Data)["field"])
    ) == {"a", "g", "h", "i", "e"}


@dataclass
class BadData:
    field: int = field(metadata=merged)


def test_invalid_merged():
    with raises(TypeError):
        list(
            get_deserialization_merged_aliases(BadData, object_fields(BadData)["field"])
        )
