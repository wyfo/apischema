__all__ = ["cache", "reset", "set_size"]
import sys
from functools import lru_cache
from typing import Callable, Iterator, MutableMapping, TypeVar, cast

from apischema.utils import type_dict_wrapper

_cached: list = []

Func = TypeVar("Func", bound=Callable)


def cache(func: Func) -> Func:
    cached = cast(Func, lru_cache()(func))
    _cached.append(cached)
    return cached


def reset():
    for cached in _cached:
        cached.cache_clear()


def set_size(size: int):
    for cached in _cached:
        wrapped = cached.__wrapped__
        setattr(
            sys.modules[wrapped.__module__], wrapped.__name__, lru_cache(size)(wrapped)
        )


K = TypeVar("K")
V = TypeVar("V")


class CacheAwareDict(MutableMapping[K, V]):
    def __init__(self, wrapped: MutableMapping[K, V]):
        self.wrapped = type_dict_wrapper(wrapped)

    def __getitem__(self, key: K) -> V:
        return self.wrapped[key]

    def __setitem__(self, key: K, value: V):
        self.wrapped[key] = value
        reset()

    def __delitem__(self, key: K):
        del self.wrapped[key]

    def __len__(self) -> int:
        return len(self.wrapped)

    def __iter__(self) -> Iterator[K]:
        return iter(self.wrapped)
