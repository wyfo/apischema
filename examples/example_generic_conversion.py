import sys
from typing import Generic, List, Tuple, TypeVar

from pytest import raises

from apischema import (
    ValidationError,
    build_input_schema,
    build_output_schema,
    from_data,
    input_converter,
    output_converter,
    to_data,
)
from apischema.visitor import Unsupported

T = TypeVar("T")


class Wrapper(Generic[T]):
    def __init__(self, wrapped: T):
        self.wrapped = wrapped

    if sys.version_info >= (3, 7):
        # Method are not handled before 3.7
        @output_converter
        def _wrapped(self) -> T:
            return self.wrapped

    else:

        def _wrapped(self) -> T:
            return self.wrapped


if sys.version_info <= (3, 7):
    output_converter(Wrapper._wrapped, Wrapper[T])

U = TypeVar("U")


@input_converter
def to_wrapper(a: U) -> Wrapper[U]:
    return Wrapper(a)


def test_wrapper():
    assert from_data(Wrapper[List[int]], [0, 1]).wrapped == [0, 1]
    assert to_data(Wrapper("wrapped")) == "wrapped"
    assert (
        to_data(build_input_schema(Wrapper[int]))
        == {"type": "integer"}
        == to_data(build_output_schema(Wrapper[int]))
    )

    with raises(ValidationError):
        from_data(Wrapper[int], "wrapped")


##########################################


class Pair(Generic[T, U]):
    def __init__(self, a: T, b: U):
        self.a = a
        self.b = b


@input_converter
def pair(value: Tuple[int, T]) -> Pair[int, T]:
    a, b = value
    return Pair(a, b)


def test_pair():
    with raises(Unsupported):
        from_data(Pair[int, str], (0, ""))
    # I decided to only match exact types because of the following issue:
    # If I have a converter for Pair[int, T] and an other for Pair[T, str],
    # which one should I choose for Pair [int, str] ...
    # maybe the first/last one declared, why not, but the feature is not
    # prioritary
