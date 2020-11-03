from dataclasses import dataclass
from typing import Any, AnyStr, Generic, TypeVar, Union

from pytest import fixture, mark, raises

from apischema import deserialize
from apischema.type_vars import TypeVarResolver

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


class Double(Generic[T, U]):
    pass


class Simple(Generic[T]):
    pass


@fixture
def type_vars() -> TypeVarResolver:
    return TypeVarResolver()


@mark.parametrize("tv, expected", [(int, int), (T, Any), (AnyStr, Union[str, bytes])])
def test_type_vars_resolve_no_context(type_vars, tv, expected):
    assert type_vars.resolve(tv) == expected


def test_type_vars_specialize_no_context(type_vars):
    assert type_vars.specialize(Double) == Double[Any, Any]


def test_type_vars_context(type_vars):
    with type_vars.generic_context(Double[int, str]):
        assert type_vars.resolve(T) == int
        assert type_vars.resolve(V) == Any
        assert type_vars.specialize(Double) == Double[int, str]
        with type_vars.generic_context(Double[U, T]):
            assert type_vars.specialize(Double) == Double[str, int]
        assert type_vars.specialize(Double) == Double[int, str]


def test_type_vars_partial(type_vars):
    with type_vars.generic_context(Double[int, T]):
        assert type_vars.resolve(T) == int
        assert type_vars.resolve(U) == Any
        assert type_vars.specialize(Double) == Double[int, Any]
        with type_vars.generic_context(Double[T, str]):
            assert type_vars.specialize(Double) == Double[int, str]
        with type_vars.generic_context(Double[Simple[T], str]):
            # B[T] is not recursively resolved
            assert type_vars.specialize(Double) == Double[Simple[T], str]


def test_type_vars_nested(type_vars):
    with type_vars.generic_context(Double[int, str]):
        with type_vars.generic_context(Simple[Simple[T]]):
            with type_vars.resolve_context(T) as tv:
                assert tv == Simple[T]
                with type_vars.generic_context(Simple[T]):
                    assert type_vars.resolve(T) == int


def test_type_vars_nested_without_context(type_vars):
    with raises(AssertionError):
        with type_vars.generic_context(Double[int, str]):
            with type_vars.generic_context(Simple[Simple[T]]):
                # Without using the context
                assert type_vars.resolve(T) == Simple[T]
                with type_vars.generic_context(Simple[T]):
                    assert type_vars.resolve(T) == int


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
