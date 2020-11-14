from dataclasses import dataclass
from typing import Any, Collection, Generic, List, Mapping, TypeVar

from pytest import mark, raises

from apischema import serialize
from apischema.conversions import extra_serializer
from apischema.conversions.metadata import handle_generic_field_type
from apischema.conversions.utils import handle_generic_conversions

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class A(Generic[T]):
    a: T


class B(Generic[T, U]):
    pass


def test_substitute_type_vars():
    assert handle_generic_conversions(A[U], B[U, int]) == (A, B[T, int])
    with raises(TypeError):
        handle_generic_conversions(A[int], B[int, int])


@extra_serializer
def serialize_a(a: A[T]) -> T:
    return a.a


def test_generic_selection():
    assert serialize(A(0), conversions={A: ([T], T)}) == 0
    assert serialize(A(0), conversions={A: T}) == 0


@mark.parametrize(
    "field_type, base, other, covariant, expected",
    [
        (int, int, str, ..., str),
        (int, U, List[U], ..., List[int]),
        (T, U, List[U], ..., List[T]),
        (List[T], List[U], Mapping[str, U], ..., Mapping[str, T]),
        (List[int], List[U], Mapping[str, U], ..., Mapping[str, int]),
        (Collection[T], List[U], Mapping[str, U], True, Mapping[str, T]),
        (List[T], Collection[U], Mapping[str, U], True, Mapping[str, Any]),
        (List[T], Collection[U], Mapping[str, U], False, Mapping[str, T]),
        (Collection[T], List[U], Mapping[str, U], False, Mapping[str, Any]),
    ],
)
def test_handle_generic_field_type(field_type, base, other, covariant, expected):
    assert handle_generic_field_type(field_type, base, other, covariant) == expected
