from dataclasses import dataclass
from enum import Enum
from typing import (AbstractSet, Any, Dict, Generic, Iterable, List, Mapping,
                    NewType, Optional, Sequence, Set, TypeVar, Union)
from unittest.mock import MagicMock, Mock

from pytest import mark, raises
from typing_extensions import Literal

from src.model import Model
from src.visitor import Unsupported, Visitor


class TestEnum(Enum):
    A = "a"
    B = "b"


@mark.parametrize("cls, method, args", [
    (int, Visitor.primitive, (int,)),
    (str, Visitor.primitive, (str,)),
    (List[int], Visitor.iterable, (list, int)),
    (Sequence[int], Visitor.iterable, (tuple, int)),
    (AbstractSet[int], Visitor.iterable, (frozenset, int)),
    (Set[int], Visitor.iterable, (set, int)),
    (Mapping[str, int], Visitor.mapping, (str, int)),
    (Dict[str, int], Visitor.mapping, (str, int)),
    (TestEnum, Visitor.enum, (TestEnum,)),
    (Literal[1, 2], Visitor.literal, ((1, 2),)),
    (Optional[int], Visitor.optional, (int,)),
    (Union[int, str], Visitor.union, ((int, str),)),
    (Any, Visitor.any, ()),
])
def test_basic_types(cls, method, args):
    visitor = Mock()
    Visitor.visit(visitor, cls, None, ())
    getattr(visitor, method.__name__) \
        .assert_called_once_with(*(*args, None, ()))


@dataclass
class TestDataclass:
    a: int
    b: str


class TestModel(Model[Sequence[str]]):
    pass


@mark.parametrize("cls, method, args", [
    (TestDataclass, Visitor.dataclass, (TestDataclass,)),
    (TestModel, Visitor.model, (TestModel,)),
])
def test_complex_types(cls, method, args):
    visitor = Mock()
    visitor.with_class_context.return_value = 0
    Visitor.visit(visitor, cls, None, ())
    getattr(visitor, method.__name__).assert_called_once_with(*(*args, 0, ()))


T = TypeVar("T")


@dataclass
class TestGeneric(Generic[T]):
    attr: T


def test_generic():
    visitor = MagicMock()
    visitor._nested.__enter__.return_value = None
    visitor._nested.__exit__.return_value = None
    Visitor.visit(visitor, TestGeneric[int], None, ())
    visitor.visit.assert_called_once_with(TestGeneric, None, ())


def test_type_var():
    visitor = Mock()
    visitor._generics = {T: int}
    Visitor.visit(visitor, T, None, ())
    visitor.visit.assert_called_once_with(int, None, ())


def test_new_type():
    visitor = Mock()
    int2 = NewType("int2", int)
    Visitor.visit(visitor, int2, None, ())
    visitor.visit.assert_called_once_with(int, None, ())


@mark.parametrize("cls, name", [
    (Iterable[str], "Iterable"),
    (Generic, "Generic"),
    (0, "0"),
    (lambda: None, "<lambda>")
])
def test_errors(cls, name):
    with raises(Unsupported, match=f"Unsupported '{name}' type"):
        Visitor.visit(Mock(), cls, None, ())
