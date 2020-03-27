from typing import Generic, TypeVar

from apischema.conversion import substitute_type_vars

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


class A(Generic[T, U]):
    pass


class B(Generic[T]):
    pass


def test_substitute_type_vars():
    assert substitute_type_vars(A[int, V], B[V]) == (A[int, U], B[U])
