import collections.abc
import sys
from dataclasses import dataclass
from typing import Any, Collection, Generic, List, Mapping, TypeVar

from pytest import mark, raises

from apischema import serialize
from apischema.conversions import extra_serializer
from apischema.conversions.metadata import Variance, handle_generic_field_type
from apischema.conversions.converters import handle_generic_conversions

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class A(Generic[T]):
    a: T


class B(Generic[T, U]):
    pass


def test_handle_generic_conversions():
    assert handle_generic_conversions(A[U], B[U, int]) == (A, B[T, int])
    with raises(TypeError):
        handle_generic_conversions(A[int], B[int, int])


@extra_serializer
def serialize_a(a: A[T]) -> T:
    return a.a


def test_generic_selection():
    assert serialize(A(0), conversions={A: ([T], T)}) == 0
    assert serialize(A(0), conversions={A: T}) == 0


COVARIANT = Variance.COVARIANT
CONTRAVARIANT = Variance.CONTRAVARIANT

py39_params: List = []
if sys.version_info >= (3, 9):
    collection = collections.abc.Collection
    py39_params = [
        (int, U, list[U], ..., list[int]),
        (T, U, list[U], ..., list[T]),
        (list[T], list[U], dict[str, U], ..., dict[str, T]),
        (list[int], list[U], dict[str, U], ..., dict[str, int]),
        (collection[T], list[U], dict[str, U], COVARIANT, dict[str, T]),
        (list[T], collection[U], dict[str, U], COVARIANT, dict[str, Any]),
        (list[T], collection[U], dict[str, U], CONTRAVARIANT, dict[str, T]),
        (collection[T], list[U], dict[str, U], CONTRAVARIANT, dict[str, Any]),
    ]


@mark.parametrize(
    "field_type, base, other, variance, expected",
    [
        (int, int, str, ..., str),
        (int, U, List[U], ..., List[int]),
        (T, U, List[U], ..., List[T]),
        (List[T], List[U], Mapping[str, U], ..., Mapping[str, T]),
        (List[int], List[U], Mapping[str, U], ..., Mapping[str, int]),
        (Collection[T], List[U], Mapping[str, U], COVARIANT, Mapping[str, T]),
        (List[T], Collection[U], Mapping[str, U], COVARIANT, Mapping[str, Any]),
        (List[T], Collection[U], Mapping[str, U], CONTRAVARIANT, Mapping[str, T]),
        (Collection[T], List[U], Mapping[str, U], CONTRAVARIANT, Mapping[str, Any]),
        *py39_params,
    ],
)
def test_handle_generic_field_type(field_type, base, other, variance, expected):
    assert handle_generic_field_type(field_type, base, other, variance) == expected
