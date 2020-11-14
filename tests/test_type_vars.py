from dataclasses import dataclass
from typing import Any, AnyStr, Deque, Generic, TypeVar, Union

from pytest import mark

from apischema import deserialize
from apischema.type_vars import get_parameters, resolve_type_vars, type_var_context
from apischema.typing import get_origin

T = TypeVar("T")
U = TypeVar("U")


class Foo(Generic[T]):
    pass


@mark.parametrize(
    "ctx, tv, expected",
    [
        (None, int, int),
        (None, T, Any),
        (None, AnyStr, Union[str, bytes]),
        (None, Foo[T], Foo[Any]),
        ({T: int}, int, int),
        ({T: int}, T, int),
        ({T: int}, Foo[T], Foo[int]),
    ],
)
def test_resolve_type_vars_no_context(ctx, tv, expected):
    assert resolve_type_vars(tv, ctx) == expected


T0 = next(iter(get_parameters(get_origin(Deque[Any]))))


@mark.parametrize(
    "ctx, cls, expected",
    [
        (None, Foo[int], {T: int}),
        (None, Foo[U], {T: Any}),
        ({T: int}, Foo[T], {T: int}),
        (None, Deque[T], {T0: Any}),
        ({T: int}, Deque[T], {T0: int}),
    ],
)
def test_type_vars_context(ctx, cls, expected):
    assert type_var_context(cls, ctx) == expected


@dataclass
class C(Generic[T]):
    c: T


@dataclass
class B(Generic[T]):
    b: T


@dataclass
class A(Generic[T]):
    a: B[B[C[T]]]


def test_reused_type_var():
    assert deserialize(A[int], {"a": {"b": {"b": {"c": 0}}}}) == A(B(B(C(0))))
