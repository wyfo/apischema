# flake8: noqa
# type: ignore
import asyncio
import inspect
import json
import sys
import timeit
import typing
from typing import *
from unittest.mock import MagicMock

from apischema.typing import Annotated, Literal, TypedDict, get_args

typing.Annotated, typing.Literal, typing.TypedDict = Annotated, Literal, TypedDict
if sys.version_info < (3, 9):

    class CollectionABC:
        def __getattribute__(self, name):
            return globals()[name] if name in globals() else MagicMock()

    sys.modules["collections.abc"] = CollectionABC()
    del CollectionABC


class Wrapper:
    def __init__(self, cls):
        self.cls = cls
        self.implem = cls.__origin__ or cls.__extra__  # extra in 3.6

    def __getitem__(self, item):
        return self.cls[item]

    def __call__(self, *args, **kwargs):
        return self.implem(*args, **kwargs)

    def __instancecheck__(self, instance):
        return isinstance(instance, self.implem)

    def __subclasscheck__(self, subclass):
        return issubclass(subclass, self.implem)


for cls in (Dict, List, Set, FrozenSet, Tuple, Type):  # noqa
    wrapper = Wrapper(cls)
    globals()[wrapper.implem.__name__] = wrapper

Set = AbstractSet

del Wrapper

if sys.version_info < (3, 7):
    asyncio.run = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

inspect.isclass = lambda tp: isinstance(tp, type) and not get_args(tp)
__timeit = timeit.timeit
timeit.timeit = lambda stmt, number=None, **kwargs: __timeit(stmt, number=1, **kwargs)

sys.modules["orjson"] = json
