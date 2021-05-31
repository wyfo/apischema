__all__ = ["cache", "reset_cache", "set_cache_size"]
import sys
from functools import lru_cache
from typing import Any, Callable, List, TypeVar, cast

_cached: List = []

Func = TypeVar("Func", bound=Callable)


def cache(func: Func) -> Func:
    if func.__qualname__.count(".") > 1:
        raise ValueError("Cached function must be declared at module level")
    cached: Any = lru_cache()(func)
    _cached.append(cached)
    return cast(Func, cached)


def reset_cache():
    for cached in _cached:
        cached.cache_clear()


def set_cache_size(size: int):
    for cached in _cached:
        wrapped = cached.__wrapped__
        setattr(
            sys.modules[wrapped.__module__], wrapped.__name__, lru_cache(size)(wrapped)
        )
