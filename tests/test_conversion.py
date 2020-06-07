from typing import Generic, TypeVar

from pytest import raises

from apischema.conversion.utils import substitute_type_vars

T = TypeVar("T")
U = TypeVar("U")


class A(Generic[T]):
    pass


class B(Generic[T, U]):
    pass


def test_substitute_type_vars():
    assert substitute_type_vars(A[U], B[U, int]) == (A, B[T, int])
    with raises(TypeError):
        substitute_type_vars(A[int], B[int, int])
