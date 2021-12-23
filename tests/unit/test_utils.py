import collections.abc
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache, wraps
from itertools import repeat
from typing import (
    AbstractSet,
    Awaitable,
    Collection,
    Dict,
    Generic,
    List,
    Mapping,
    Set,
    Tuple,
    TypeVar,
)
from unittest.mock import Mock

import pytest

from apischema.typing import Annotated, typing_origin
from apischema.utils import (
    deprecate_kwargs,
    is_async,
    replace_builtins,
    to_camel_case,
    type_dict_wrapper,
)


def test_to_camel_case():
    assert to_camel_case("min_length") == "minLength"


def sync_func():
    ...


async def async_func():
    ...


def func_not_returning_awaitable() -> int:
    ...


def func_returning_awaitable() -> Awaitable[int]:
    ...


sync_cases = [
    sync_func,
    wraps(sync_func)(lambda: sync_func()),
    lru_cache()(sync_func),
    func_not_returning_awaitable,
]
async_cases = [
    async_func,
    wraps(async_func)(lambda: async_func()),
    lru_cache()(async_func),
    func_returning_awaitable,
]


@pytest.mark.parametrize(
    "func, expected", [*zip(sync_cases, repeat(False)), *zip(async_cases, repeat(True))]
)
def test_is_async(func, expected):
    assert is_async(func) == expected


@pytest.mark.parametrize(
    "types, expected",
    [
        ({}, False),
        ({"return": int}, False),
        ({"return": Awaitable[int]}, True),
        ({"return": Annotated[int, ...]}, False),
        ({"return": Annotated[Awaitable[int], ...]}, True),
    ],
)
def test_is_async_with_types(types, expected):
    assert is_async(lambda: ..., types) == expected


T = TypeVar("T")


class GenericClass(Generic[T]):
    pass


if sys.version_info < (3, 7):
    typing_origin_cases = [(List, List), (Collection, Collection)]
elif (3, 7) <= sys.version_info < (3, 9):
    typing_origin_cases = [(list, List), (collections.abc.Collection, Collection)]
else:
    typing_origin_cases = [
        (list, list),
        (collections.abc.Collection, collections.abc.Collection),
        (List, List),
        (Collection, Collection),
    ]


@pytest.mark.parametrize(
    "tp, expected", [*typing_origin_cases, (GenericClass, GenericClass)]
)
def test_typing_origin(tp, expected):
    assert typing_origin(tp) == expected


if sys.version_info < (3, 9):
    replace_builtins_cases = [
        (Collection[int], List[int]),
        (AbstractSet[int], Set[int]),
        (Tuple[int], Tuple[int]),
        (Mapping[int, int], Dict[int, int]),
    ]
else:
    replace_builtins_cases = [
        (Collection[int], list[int]),
        (AbstractSet[int], set[int]),
        (Tuple[int], tuple[int]),
        (Mapping[int, int], dict[int, int]),
        (collections.abc.Collection[int], list[int]),
        (set[int], set[int]),
        (tuple[int], tuple[int]),
        (dict[int, int], dict[int, int]),
    ]


@pytest.mark.parametrize("annotated", [False, True])  # type: ignore
@pytest.mark.parametrize("wrapped", [False, True])  # type: ignore
@pytest.mark.parametrize("tp, expected", replace_builtins_cases)
def test_replace_builtins(tp, expected, annotated, wrapped):
    if wrapped:
        tp = Collection[tp]
        expected = (list if sys.version_info >= (3, 9) else List)[expected]
    if annotated:
        tp, expected = Annotated[tp, 0], Annotated[expected, 0]
    assert replace_builtins(tp) == expected


@pytest.mark.parametrize("wrapped", [{}, defaultdict(list)])
def test_type_dict_wrapper(wrapped):
    wrapper = type_dict_wrapper(wrapped)

    class A:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            if getattr(cls, "__origin__", None) is not None:
                return
            wrapper.setdefault(cls, []).append(cls)

    class B(A):
        pass

    class C(A, Generic[T]):
        pass

    class D(C[int]):
        pass

    assert sorted(wrapper.items(), key=lambda i: i[0].__name__) == [
        (B, [B]),
        (C, [C]),
        (D, [D]),
    ]


@deprecate_kwargs({"prev": "new"})
@dataclass
class MyClass:
    new: int


@deprecate_kwargs({"prev": "new"})
def func(new: int):
    pass


@pytest.mark.parametrize("func", [MyClass, func])
@pytest.mark.parametrize("kwarg, warn", [("prev", True), ("new", False)])
def test_deprecate_kwargs(monkeypatch, func, kwarg, warn):
    mock = Mock()
    monkeypatch.setattr(warnings, "warn", mock)
    func(**{kwarg: 0})
    mock.assert_called_once() if warn else mock.assert_not_called()
