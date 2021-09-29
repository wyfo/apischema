from dataclasses import dataclass
from typing import Generic, TypeVar

from pytest import raises

from apischema import ValidationError, deserialize
from apischema.typing import Annotated

T = TypeVar("T")


@dataclass
class A(Generic[T]):
    a: T


@dataclass
class B(Generic[T]):
    b: T


def a_to_b(a: A[T]) -> B[T]:
    return B(a.a)


def test_generic_conversion():
    assert deserialize(B[int], {"a": 0}, conversion=a_to_b) == B(0)
    with raises(ValidationError):
        deserialize(B[int], {"a": ""}, conversion=a_to_b)


def a_to_b_unparametrized(a: A) -> B:
    return B(a.a)


def test_unparameterized_generic_conversion():
    # With unparametrized conversion, generic args are lost
    assert deserialize(B[int], {"a": ""}, conversion=a_to_b_unparametrized) == B("")


def a_to_b_annotated(a: Annotated[A[T], "a"]) -> B[T]:
    return B(a.a)


def test_annotated_generic_conversion():
    assert deserialize(B[int], {"a": 0}, conversion=a_to_b_annotated) == B(0)
    with raises(ValidationError):
        deserialize(B[int], {"a": ""}, conversion=a_to_b_annotated)
