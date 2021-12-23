from dataclasses import dataclass, field
from typing import List, Optional

import pytest

from apischema import settings
from apischema.conversions import Conversion, LazyConversion
from apischema.metadata import conversion
from apischema.recursion import DeserializationRecursiveChecker, is_recursive


class A:
    pass


@dataclass
class B:
    b: Optional["B"]


@dataclass
class C:
    b: B
    d: "D"
    f: "F"


@dataclass
class D:
    c: List[C]


@dataclass
class E:
    c: List[C]


@dataclass
class F:
    e: E


rec_conv = None


@dataclass
class G:
    a: Optional[A] = field(
        metadata=conversion(deserialization=LazyConversion(lambda: rec_conv))
    )


rec_conv = Conversion(lambda _: None, source=Optional[G], target=A)


@pytest.mark.parametrize(
    "tp, expected",
    [(A, False), (B, True), (C, True), (D, True), (E, True), (F, True), (G, True)],
)
def test_is_recursive(tp, expected):
    assert (
        is_recursive(
            tp,
            None,
            settings.deserialization.default_conversion,
            DeserializationRecursiveChecker,
        )
        == expected
    )
