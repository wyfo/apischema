import collections.abc
import sys
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

import pytest

from apischema.typing import Annotated, typing_origin
from apischema.utils import is_async, replace_builtins, to_camel_case


def test_to_camel_case():
    assert to_camel_case("min_length") == "minLength"


def sync_func(): ...


async def async_func(): ...


def func_not_returning_awaitable() -> int:  # type: ignore
    ...


def func_returning_awaitable() -> Awaitable[int]:  # type: ignore
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


if sys.version_info < (3, 9):
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
        (Tuple[int, ...], List[int]),
    ]
else:
    replace_builtins_cases = [
        (Collection[int], list[int]),
        (AbstractSet[int], set[int]),
        (Tuple[int], tuple[int]),
        (Mapping[int, int], dict[int, int]),
        (Tuple[int, ...], list[int]),
        (collections.abc.Collection[int], list[int]),
        (set[int], set[int]),
        (tuple[int], tuple[int]),
        (dict[int, int], dict[int, int]),
        (tuple[int, ...], list[int]),
    ]


@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("tp, expected", replace_builtins_cases)
def test_replace_builtins(tp, expected, annotated, wrapped):
    if wrapped:
        tp = Collection[tp]  # type: ignore
        expected = (list if sys.version_info >= (3, 9) else List)[expected]  # type: ignore
    if annotated:
        tp, expected = Annotated[tp, 0], Annotated[expected, 0]
    assert replace_builtins(tp) == expected
