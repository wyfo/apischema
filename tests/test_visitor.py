import collections
import sys
from dataclasses import dataclass
from enum import Enum
from types import MethodType
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
    Sized,
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
    mock = Mock()
    Visitor.__init__(mock)
    mock._generic = MethodType(Visitor._generic, mock)
    for method in (Visitor.visit_not_builtin, Visitor._unsupported):
        setattr(mock, method.__name__, MethodType(method, mock))
    return mock


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
    (Sized, Visitor.unsupported, [Sized]),
]
py37 = [
    (List[int], Visitor.collection, [list, int]),
    (Tuple[str, ...], Visitor.collection, [tuple, str]),
    (Collection[int], Visitor.collection, [collections.abc.Collection, int]),
    (Mapping[str, int], Visitor.mapping, [collections.abc.Mapping, str, int]),
    (Dict[str, int], Visitor.mapping, [dict, str, int]),
    (Sized, Visitor.unsupported, [collections.abc.Sized]),
]


@mark.parametrize(
    "cls, method, args",
    [
        *(py37 if sys.version_info >= (3, 7) else py36),
        (Annotated[int, 42, "42"], Visitor.annotated, [int, (42, "42")]),
        (Any, Visitor.any, []),
        (DataclassExample, Visitor.dataclass, [DataclassExample]),
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
            (TypedDictExample, {"key1": str, "key2": List[int]}, True),
        ),
        (Optional[int], Visitor.union, [(int, NoneType)]),
        (Union[int, str], Visitor.union, [(int, str)]),
    ],
)
def test_visitor(visitor, cls, method, args):
    Visitor.visit(visitor, cls, ARG)
    getattr(visitor, method.__name__).assert_called_once_with(*args, ARG)


T = TypeVar("T")


class UnsupportedGeneric(Generic[T]):
    pass


def test_unsupported(visitor):
    Visitor.visit(visitor, Mock, ARG)
    visitor.unsupported.assert_called_once_with(Mock, ARG)
    visitor.reset_mock()

    Visitor.visit(visitor, UnsupportedGeneric, ARG)
    visitor.unsupported.assert_called_once_with(UnsupportedGeneric[Any], ARG)
    visitor.reset_mock()

    visitor._generics[T] = [int]
    Visitor.visit(visitor, UnsupportedGeneric, ARG)
    visitor.unsupported.assert_called_once_with(UnsupportedGeneric[int], ARG)


@dataclass
class GenericExample(Generic[T]):
    attr: T


@mark.parametrize(
    "cls, generics, expected",
    [
        (int, {}, {T: [int]}),
        (int, {T: [str]}, {T: [str, int]}),
        (T, {T: [str]}, {T: [str, T]}),
    ],
)
def test_generic(visitor, cls, generics, expected):
    def visit(*args):
        assert visitor._generics == expected

    visitor.visit = visit
    visitor._generics.update(generics)
    Visitor._generic(visitor, GenericExample[cls], ARG)
    assert visitor._generics == {T: [], **generics}


@mark.parametrize(
    "type_var, generics, expected",
    [
        (T, {T: [int, str]}, str),
        (T, {}, Any),  # type: ignore
        (TypeVar("T", bound=int), {}, Any),  # type: ignore
        # constraints are handled (AnyStr for example)
        (TypeVar("T", int, str), {}, Union[int, str]),  # type: ignore
    ],
)
def test_type_var(visitor, type_var, generics, expected):
    visitor._generics.update(generics)
    Visitor._type_var(visitor, type_var, ARG)
    visitor.visit.assert_called_once_with(expected, ARG)


class Custom:
    pass


def test_default_implementations(visitor):
    assert Visitor.annotated(visitor, int, (42,), ARG)
    visitor.visit.assert_called_once_with(int, ARG)
    visitor.reset_mock()

    assert Visitor.new_type(visitor, ..., int, ARG)
    visitor.visit.assert_called_once_with(int, ARG)
    visitor.reset_mock()

    with raises(Unsupported) as err:
        Visitor.unsupported(..., Generic, ARG)
    assert err.value.cls == Generic
    with raises(Unsupported) as err:
        Visitor.unsupported(
            ..., Generic[T], ARG,
        )
    assert err.value.cls == Generic[T]

    with raises(NotImplementedError):
        Visitor.named_tuple(..., ..., ..., ..., ...)
