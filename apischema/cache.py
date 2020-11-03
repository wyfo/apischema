from functools import lru_cache
from typing import Any, Callable, List, TypeVar, cast

_cached: List = []

Func = TypeVar("Func", bound=Callable)


def cache(func: Func) -> Func:
    cached: Any = lru_cache()(func)
    _cached.append(cached)
    return cast(Func, cached)


def reset_cache():
    for cached in _cached:
        cached.cache_clear()
