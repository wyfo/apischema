from typing import Callable, Collection, Generic, List, Mapping, Sequence, TypeVar, cast

from pytest import mark

from apischema.conversions import Conversion
from apischema.conversions.conversions import ResolvedConversion
from apischema.types import AnyType
from apischema.utils import subtyping_substitution

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
    "supertype, subtype, super_to_sub, sub_to_super",
    [
        (A[U, T], A[int, str], {U: int, T: str}, {}),
        (A, A[str, int], {T: str, U: int}, {}),
        (B[T], C, {T: int}, {}),
        (Sequence[T], List[str], {T: str}, {}),
        #
        (B[str], B[T], {}, {T: str}),
        (B[int], B, {}, {V: int}),
        (B[str], D[T], {}, {T: str}),
        (Collection[str], Mapping[T, int], {}, {T: str}),
    ],
)
def test_subtyping_substitution(supertype, subtype, super_to_sub, sub_to_super):
    assert subtyping_substitution(supertype, subtype) == (super_to_sub, sub_to_super)
