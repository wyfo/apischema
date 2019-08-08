from typing import AbstractSet, List, NewType, Sequence, Set, TypeVar

from pytest import mark

from src.types import iterable_type, type_name


@mark.parametrize("cls, expected", [
    (List[str], list),
    (Sequence[str], tuple),
    (AbstractSet[str], frozenset),
    (Set[str], set),
])
def test_iterable_type(cls, expected):
    # noinspection PyUnresolvedReferences
    assert iterable_type(cls.__origin__) == expected


T = TypeVar("T")


@mark.parametrize("cls, expected", [
    (int, "int"),
    (List[str], "List"),
    (T, "T"),
    (NewType("int2", int), "int2")
])
def test_type_name(cls, expected):
    assert type_name(cls) == expected
