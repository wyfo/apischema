import collections.abc
import sys
from dataclasses import dataclass
from typing import Collection, Generic, List, Mapping, TypeVar

from pytest import mark, raises

from apischema.conversions.fields import Variance, handle_generic_field_type
from apischema.conversions.utils import get_conversion_type

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class A(Generic[T]):
    a: T


class B(Generic[T, U]):
    pass


def test_handle_generic_conversions():
    assert get_conversion_type(A[U], B[U, int]) == (A, B[T, int])
    with raises(TypeError):
        get_conversion_type(A[int], B[int, int])


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
        (list[T], collection[U], dict[str, U], COVARIANT, dict[str, U]),
        (list[T], collection[U], dict[str, U], CONTRAVARIANT, dict[str, T]),
        (collection[T], list[U], dict[str, U], CONTRAVARIANT, dict[str, U]),
    ]


@mark.parametrize(
    "field_type, base, other, variance, expected",
    [
        (List[int], List[U], Mapping[str, U], ..., Mapping[str, int]),
        (int, int, str, ..., str),
        (int, U, List[U], ..., List[int]),
        (T, U, List[U], ..., List[T]),
        (List[T], List[U], Mapping[str, U], ..., Mapping[str, T]),
        (List[int], List[U], Mapping[str, U], ..., Mapping[str, int]),
        (Collection[T], List[U], Mapping[str, U], COVARIANT, Mapping[str, T]),
        (List[T], Collection[U], Mapping[str, U], COVARIANT, Mapping[str, U]),
        (List[T], Collection[U], Mapping[str, U], CONTRAVARIANT, Mapping[str, T]),
        (Collection[T], List[U], Mapping[str, U], CONTRAVARIANT, Mapping[str, U]),
        *py39_params,
    ],
)
def test_handle_generic_field_type(field_type, base, other, variance, expected):
    assert handle_generic_field_type(field_type, base, other, variance) == expected
