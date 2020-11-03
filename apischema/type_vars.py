from collections import defaultdict
from contextlib import contextmanager
from typing import Any, DefaultDict, List, TypeVar, Union

from apischema.types import AnyType
from apischema.typing import get_args, get_origin


class TypeVarResolver:
    def __init__(self):
        self.type_vars: DefaultDict[TypeVar, List[AnyType]] = defaultdict(list)

    @contextmanager
    def generic_context(self, cls: AnyType):
        origin, args = get_origin(cls), get_args(cls)
        if origin is None:
            yield
            return
        if not hasattr(origin, "__parameters__"):
            raise TypeError(f"{cls} origin has no parameters")
        assert len(origin.__parameters__) == len(args)
        # Use a side effect in order to avoid passing argument anywhere
        for tv, arg in zip(origin.__parameters__, list(map(self.resolve, args))):
            self.type_vars[tv].append(arg)
        try:
            yield
        finally:
            for tv in origin.__parameters__:
                self.type_vars[tv].pop()

    @contextmanager
    def resolve_context(self, tv: Any) -> Any:
        stack = []
        while isinstance(tv, TypeVar):  # type: ignore
            try:
                cls = self.type_vars[tv].pop()
            except IndexError:
                tv = Union[tv.__constraints__] if tv.__constraints__ else Any
            else:
                stack.append((tv, cls))
                tv = cls
        try:
            yield tv
        finally:
            for tv, cls in reversed(stack):
                self.type_vars[tv].append(cls)

    def resolve(self, tv: Any) -> Any:
        with self.resolve_context(tv) as result:
            return result

    def specialize(self, cls: AnyType):
        if not hasattr(cls, "__parameters__") or not cls.__parameters__:
            return cls
        else:
            return cls[tuple(map(self.resolve, get_args(cls) or cls.__parameters__))]
