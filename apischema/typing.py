"""Kind of typing_extensions for this package"""
__all__ = [
    "Annotated",
    "Literal",
    "TypedDict",
    "_AnnotatedAlias",
    "_GenericAlias",
    "_LiteralMeta",
    "_TypedDictMeta",
    "get_type_hints",
]

import sys
from types import ModuleType
from typing import Any, Generic, TypeVar


class NoType:
    def __getitem__(self, key):  # pragma: no cover
        return self


NO_TYPE: Any = NoType()

if sys.version_info >= (3, 9):  # pragma: no cover
    from typing import Annotated, get_type_hints
else:  # pragma: no cover
    try:
        from typing_extensions import Annotated
    except ImportError:
        Annotated = NO_TYPE
    try:
        from typing_extensions import get_type_hints as gth
    except ImportError:
        from typing import get_type_hints as _gth

        def gth(  # type: ignore
            obj, globalns=None, localns=None, include_extras=False
        ):
            return _gth(obj, globalns, localns)

    def get_type_hints(  # type: ignore
        obj, globalns=None, localns=None, include_extras=False
    ):
        # fix https://bugs.python.org/issue37838
        if not isinstance(obj, (type, ModuleType)) and globalns is None:
            nsobj = obj
            while hasattr(nsobj, "__wrapped__"):
                nsobj = nsobj.__wrapped__
            globalns = getattr(nsobj, "__globals__", None)
        localns = {"unicode": str, **(localns or {})}
        return gth(obj, globalns, localns, include_extras)


if sys.version_info >= (3, 8):  # pragma: no cover
    from typing import Literal, TypedDict, Protocol  # noqa F401
else:  # pragma: no cover
    try:
        from typing_extensions import Literal, TypedDict, Protocol  # noqa F401
    except ImportError:
        Literal = NO_TYPE
        TypedDict = NO_TYPE

Annotated = Annotated
Literal = Literal
TypedDict = TypedDict

_T = TypeVar("_T")
_AnnotatedAlias = type(Annotated[_T, ...])
_GenericAlias = type(Generic[_T])
_LiteralMeta = type(Literal)
_TypedDictMeta = type(TypedDict)
