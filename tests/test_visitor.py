import collections
import sys
from dataclasses import dataclass, fields
from enum import Enum
from typing import (
    Any,
    Collection,
    Dict,
    Generic,
    List,
    Mapping,
    NamedTuple,
    NewType,
    Optional,
    Tuple,
    TypeVar,
    Union,
)
from unittest.mock import Mock

from pytest import fixture, mark, raises

from apischema.types import NoneType
from apischema.typing import Annotated, Literal, TypedDict
from apischema.visitor import Unsupported, Visitor

ARG = object()


@fixture
def visitor() -> Mock:
    return Mock()


class NamedTupleExample(NamedTuple):
    a: int
    b: str = ""


class EnumExample(Enum):
    A = "a"
    B = "b"


NewTypeExample = NewType("NewTypeExample", int)


def func():
    pass


@dataclass
class DataclassExample:
    a: int
    b: str


class TypedDictExample(TypedDict, total=True):
    key1: str
    key2: List[int]


class MyInt(int):
    pass


py36 = [
    (List[int], Visitor.collection, [List, int]),
    (Tuple[str, ...], Visitor.collection, [Tuple, str]),
    (Collection[int], Visitor.collection, [Collection, int]),
    (Mapping[str, int], Visitor.mapping, [Mapping, str, int]),
    (Dict[str, int], Visitor.mapping, [Dict, str, int]),
]
py37 = [
    (List[int], Visitor.collection, [list, int]),
    (Tuple[str, ...], Visitor.collection, [tuple, str]),
    (Collection[int], Visitor.collection, [collections.abc.Collection, int]),
    (Mapping[str, int], Visitor.mapping, [collections.abc.Mapping, str, int]),
    (Dict[str, int], Visitor.mapping, [dict, str, int]),
]

pep_585: list = []
if sys.version_info >= (3, 9):
    pep_585 = [
        (list[int], Visitor.collection, [list, int]),
        (tuple[str, ...], Visitor.collection, [tuple, str]),  # type: ignore
        (
            collections.abc.Collection[int],
            Visitor.collection,
            [collections.abc.Collection, int],
        ),
        (
            collections.abc.Mapping[str, int],
            Visitor.mapping,
            [collections.abc.Mapping, str, int],
        ),
        (dict[str, int], Visitor.mapping, [dict, str, int]),
    ]

py310: list = []
if sys.version_info >= (3, 10):
    py310 = [(int | str, Visitor.union, [(int, str)])]


@mark.parametrize(
    "cls, method, args",
    [
        *(py37 if sys.version_info >= (3, 7) else py36),
        *pep_585,
        *py310,
        (Annotated[int, 42, "42"], Visitor.annotated, [int, (42, "42")]),
        (Any, Visitor.any, []),
        (
            DataclassExample,
            Visitor.dataclass,
            [
                DataclassExample,
                {"a": int, "b": str},
                (fields(DataclassExample)[0], fields(DataclassExample)[1]),
                (),
            ],
        ),
        (EnumExample, Visitor.enum, [EnumExample]),
        (Literal[1, 2], Visitor.literal, [(1, 2)]),
        (
            NamedTupleExample,
            Visitor.named_tuple,
            [NamedTupleExample, {"a": int, "b": str}, {"b": ""}],
        ),
        (NewTypeExample, Visitor.new_type, [NewTypeExample, int]),
        (int, Visitor.primitive, [int]),
        (str, Visitor.primitive, [str]),
        (MyInt, Visitor.subprimitive, [MyInt, int]),
        (Tuple[str, int], Visitor.tuple, [(str, int)]),
        (
            TypedDictExample,
            Visitor.typed_dict,
            (TypedDictExample, {"key1": str, "key2": List[int]}, {"key1", "key2"}),
        ),
        (Optional[int], Visitor.union, [(int, NoneType)]),
        (Union[int, str], Visitor.union, [(int, str)]),
    ],
)
def test_visitor(visitor, cls, method, args):
    Visitor.visit(visitor, cls)
    getattr(visitor, method.__name__).assert_called_once_with(*args)


T = TypeVar("T")


@dataclass
class GenericExample(Generic[T]):
    attr: T


def test_default_implementations(visitor):
    assert Visitor.annotated(visitor, int, (42,))
    visitor.visit.assert_called_once_with(int)
    visitor.reset_mock()

    assert Visitor.new_type(visitor, ..., int)
    visitor.visit.assert_called_once_with(int)
    visitor.reset_mock()

    with raises(Unsupported) as err:
        Visitor.unsupported(..., Generic)
    assert err.value.type == Generic
    with raises(Unsupported) as err:
        Visitor.unsupported(..., Generic[T])
    assert err.value.type == Generic[T]

    with raises(NotImplementedError):
        Visitor.named_tuple(..., ..., ..., ...)
