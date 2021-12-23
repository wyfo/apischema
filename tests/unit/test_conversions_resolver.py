from typing import Collection, Dict, List, Mapping, Sequence, Tuple

import pytest

from apischema import serializer, settings
from apischema.conversions.conversions import Conversion, LazyConversion
from apischema.conversions.visitor import SerializationVisitor
from apischema.json_schema.conversions_resolver import (
    WithConversionsResolver,
    merge_results,
)
from apischema.objects import set_object_fields
from apischema.types import AnyType
from apischema.utils import identity


@pytest.mark.parametrize(
    "results, origin, expected",
    [
        ([[int]], Collection, [[int]]),
        ([[int, str], [str]], Mapping, [[int, str], [str, str]]),
        ([[int], []], Mapping, []),
    ],
)
def test_merge_results(results, origin, expected):
    assert list(merge_results(results, origin)) == [
        origin[tuple(exp)] for exp in expected
    ]


class Visitor(SerializationVisitor, WithConversionsResolver):
    def visit(self, tp: AnyType) -> Sequence[AnyType]:
        return self.resolve_conversion(tp)


class A:
    pass


serializer(Conversion(id, source=A, target=int))

tmp = None
rec_conversion = Conversion(identity, A, Collection[A], LazyConversion(lambda: tmp))
tmp = rec_conversion


class B:
    pass


set_object_fields(B, [])


@pytest.mark.parametrize(
    "tp, conversions, expected",
    [
        (int, None, [int]),
        (int, Conversion(str, int), []),
        (List[int], None, [Collection[int]]),
        (List[int], Conversion(str, source=int), [Collection[str]]),
        (
            Tuple[Dict[int, str], ...],
            [Conversion(str, source=int), Conversion(bool, source=str)],
            [Collection[Mapping[str, bool]]],
        ),
        (
            List[int],
            Conversion(str, source=int, sub_conversion=Conversion(bool, source=str)),
            [Collection[bool]],
        ),
        (A, None, [A]),
        (Collection[A], None, [Collection[A], Collection[int]]),
        (A, rec_conversion, []),
        (B, None, [B]),
    ],
)
def test_resolve_conversion(tp, conversions, expected):
    result = Visitor(settings.serialization.default_conversion).visit_with_conv(
        tp, conversions
    )
    assert list(result) == list(expected)
