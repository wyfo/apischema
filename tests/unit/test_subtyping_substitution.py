from typing import Callable, Collection, Generic, List, Mapping, Sequence, TypeVar, cast

import pytest

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


@pytest.mark.parametrize(
    "supertype, subtype, super_to_sub, sub_to_super",
    [
        (A[U, T], A[int, str], {U: int, T: str}, {}),  # type: ignore
        (A, A[str, int], {T: str, U: int}, {}),
        (B[T], C, {T: int}, {}),  # type: ignore
        (Sequence[T], List[str], {T: str}, {}),  # type: ignore
        #
        (B[str], B[T], {}, {T: str}),  # type: ignore
        (B[int], B, {}, {V: int}),
        (B[str], D[T], {}, {T: str}),  # type: ignore
        (Collection[str], Mapping[T, int], {}, {T: str}),  # type: ignore
    ],
)
def test_subtyping_substitution(supertype, subtype, super_to_sub, sub_to_super):
    assert subtyping_substitution(supertype, subtype) == (super_to_sub, sub_to_super)
