from typing import Collection, Dict, List, Mapping, Sequence, Tuple

from pytest import mark

from apischema import serializer
from apischema.conversions import identity
from apischema.conversions.conversions import Conversion, LazyConversion
from apischema.conversions.visitor import SerializationVisitor
from apischema.json_schema.generation.conversions_resolver import (
    WithConversionsResolver,
    merge_results,
)
from apischema.types import AnyType


@mark.parametrize(
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


class TestVisitor(SerializationVisitor, WithConversionsResolver):
    def visit(self, tp: AnyType) -> Sequence[AnyType]:
        return self.resolve_conversions(tp)


class A:
    pass


serializer(Conversion(id, source=A, target=int))

tmp = None
rec_conversion = Conversion(identity, A, Collection[A], LazyConversion(lambda: tmp))
tmp = rec_conversion


@mark.parametrize(
    "tp, conversions, result",
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
            Conversion(str, source=int, sub_conversions=Conversion(bool, source=str)),
            [Collection[bool]],
        ),
        (A, None, [A]),
        (Collection[A], None, [Collection[A], Collection[int]]),
        (A, rec_conversion, []),
    ],
)
def test_resolve_conversion(tp, conversions, result):
    assert list(TestVisitor().visit_with_conversions(tp, conversions)) == list(result)
