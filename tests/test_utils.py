from functools import lru_cache, wraps
from itertools import repeat
from typing import Awaitable

from pytest import mark

from apischema.typing import Annotated
from apischema.utils import is_async, to_camel_case, to_hashable


def test_to_hashable():
    hashable1 = to_hashable({"key1": 0, "key2": [1, 2]})
    hashable2 = to_hashable({"key2": [1, 2], "key1": 0})
    assert hashable1 == hashable2
    assert hash(hashable1) == hash(hashable2)


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


@mark.parametrize(
    "func, expected", [*zip(sync_cases, repeat(False)), *zip(async_cases, repeat(True))]
)
def test_is_async(func, expected):
    assert is_async(func) == expected


@mark.parametrize(
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
