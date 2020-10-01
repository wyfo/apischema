from dataclasses import dataclass, field
from typing import Collection, Generic, List, TypeVar

from pytest import raises

from apischema.json_schema import deserialization_schema
from apischema.metadata import conversions
from apischema.conversions.utils import substitute_type_vars

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class A(Generic[T]):
    a: T


class B(Generic[T, U]):
    pass


def test_substitute_type_vars():
    assert substitute_type_vars(A[U], B[U, int]) == (A, B[T, int])
    with raises(TypeError):
        substitute_type_vars(A[int], B[int, int])


def wrap_a(a: List[U]) -> List[A[U]]:
    ...


@dataclass
class C(Generic[T]):
    a: Collection[A[T]] = field(metadata=conversions(deserializer=wrap_a))


def test_generic_conversions():
    assert deserialization_schema(C[int]) == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "additionalProperties": False,
        "properties": {"a": {"items": {"type": "integer"}, "type": "array"}},
        "required": ["a"],
        "type": "object",
    }
