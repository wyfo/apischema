from dataclasses import InitVar, dataclass, field
from typing import Generic, TypeVar

from pytest import raises

from apischema import settings
from apischema.deserialization import get_deserialization_flattened_aliases
from apischema.metadata import flatten, init_var
from apischema.objects import object_fields


@dataclass
class A:
    a: int
    b: "B" = field(metadata=flatten)
    c: "C[int]" = field(metadata=flatten)
    d: "D" = field(metadata=flatten)
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
    field: A = field(metadata=flatten)


def test_flattened_aliases():
    aliases = get_deserialization_flattened_aliases(
        Data, object_fields(Data)["field"], settings.deserialization.default_conversion
    )
    assert set(aliases) == {"a", "g", "h", "i", "e"}


@dataclass
class BadData:
    field: int = field(metadata=flatten)


def test_invalid_flattened():
    with raises(TypeError):
        list(
            get_deserialization_flattened_aliases(
                BadData, object_fields(BadData)["field"]
            )
        )
