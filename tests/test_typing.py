from typing import Generic, TypeVar
from unittest.mock import Mock

from pytest import mark

from apischema.typing import (
    _TypedDictMeta,
    generic_mro,
    required_keys,
    resolve_type_hints,
)

T = TypeVar("T")
U = TypeVar("U")


class A(Generic[T, U]):
    t: T
    u: U


class B(A[int, T]):
    v: T


class C(B[str]):
    pass


class D(C):
    pass


test_cases = [
    (A, [A], {"t": T, "u": U}),
    (A[int, str], [A[int, str]], {"t": int, "u": str}),
    (A[int, T], [A[int, T]], {"t": int, "u": T}),
    (B, [B, A[int, T]], {"t": int, "u": T, "v": T}),
    (B[U], [B[U], A[int, U]], {"t": int, "u": U, "v": U}),
    (B[str], [B[str], A[int, str]], {"t": int, "u": str, "v": str}),
    (C, [C, B[str], A[int, str]], {"t": int, "u": str, "v": str}),
    (D, [D, C, B[str], A[int, str]], {"t": int, "u": str, "v": str}),
]


@mark.parametrize("tp, result, _", test_cases)
def test_generic_mro(tp, result, _):
    assert generic_mro(tp) == (*result, Generic, object)


@mark.parametrize("tp, _, result", test_cases)
def test_resolve_type_hints(tp, _, result):
    assert resolve_type_hints(tp) == result


def test_required_keys():
    td1, td2, td3 = Mock(_TypedDictMeta), Mock(_TypedDictMeta), Mock(_TypedDictMeta)
    td1.__annotations__ = {"key": str}
    td1.__total__ = False
    td1.__bases__ = ()
    td2.__annotations__ = {"key": str, "other": int}
    td2.__total__ = True
    td2.__bases__ = (td1,)
    td3.__annotations__ = {"key": str, "other": int, "last": bool}
    td3.__total__ = False
    td3.__bases__ = (td2, object)
    assert required_keys(td1) == set()
    assert required_keys(td2) == {"other"}
    assert required_keys(td3) == {"other"}
