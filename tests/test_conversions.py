from typing import Callable, Collection, Generic, List, Mapping, Sequence, TypeVar, cast

from pytest import mark

from apischema.conversions import Conversion
from apischema.conversions.conversions import ResolvedConversion, update_generics
from apischema.types import AnyType

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


class A(Generic[T, U]):
    pass


class B(Generic[V]):
    pass


class C(B[int]):
    pass


class D(B[T]):
    pass


def conv(source: AnyType, target: AnyType) -> ResolvedConversion:
    return ResolvedConversion(Conversion(cast(Callable, ...), source, target))


@mark.parametrize(
    "conversion, tp, as_source, as_target, expected",
    [
        (conv(src, tgt), tp, True, False, conv(tp, res))
        for src, tgt, tp, res in [
            (A[U, T], B[T], A[int, str], B[str]),
            (A, B, A[int, str], B[V]),
            (B[T], A[T, str], C, A[int, str]),
            (Sequence[T], Mapping[int, T], List[str], Mapping[int, str]),
        ]
    ]
    + [
        (conv(src, tgt), tp, False, True, conv(res, tp))
        for src, tgt, tp, res in [
            (A[int, T], B[T], B[str], A[int, str]),
            (A[int, T], D[T], B[str], A[int, str]),
            (A, B, B[int], A[T, U]),
            (Mapping[int, T], Sequence[T], Collection[str], Mapping[int, str]),
        ]
    ],
)
def test_update_generic(conversion, tp, as_source, as_target, expected):
    assert update_generics(conversion, tp, as_source, as_target) == expected
