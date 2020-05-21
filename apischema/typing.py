"""Kind of typing_extensions for this package"""
__all__ = [
    "Annotated",
    "Literal",
    "NamedTupleMeta",
    "Protocol",
    "TypedDict",
    "_AnnotatedAlias",
    "_GenericAlias",
    "_LiteralMeta",
    "_TypedDictMeta",
    "get_type_hints",
    "set_type_hints",
    "_type_repr",
]

import sys
import types
from dataclasses import is_dataclass
from typing import Any, Dict, Generic, Mapping, NamedTuple, Optional, Type, TypeVar


class NoType:
    def __getitem__(self, key):
        return self


NO_TYPE: Any = NoType()

if sys.version_info >= (3, 9):
    from typing import Annotated, get_type_hints as gth
else:
    try:
        from typing_extensions import Annotated
    except ImportError:
        Annotated = NO_TYPE
    try:
        from typing_extensions import get_type_hints as gth
    except ImportError:
        from typing import get_type_hints as gth_

        def gth(obj, globalns=None, localns=None, include_extras=False):  # type: ignore
            return gth_(obj, globalns, localns)


if sys.version_info >= (3, 8):
    from typing import Literal, Protocol, TypedDict
else:
    try:
        from typing_extensions import Literal, Protocol, TypedDict
    except ImportError:
        Literal = NO_TYPE
        TypedDict = NO_TYPE
        Protocol = NO_TYPE

Annotated = Annotated
Literal = Literal
Protocol = Protocol
TypedDict = TypedDict

_T = TypeVar("_T")
_AnnotatedAlias = type(Annotated[_T, ...])
_GenericAlias = type(Generic[_T])
_LiteralMeta = type(Literal)
_TypedDictMeta = type(TypedDict)
NamedTupleMeta = type(NamedTuple)

_type_hints: Dict[str, Mapping[str, Type]] = {}

NS = Dict[str, Any]


def get_type_hints(
    obj,
    globalns: Optional[NS] = None,
    localns: Optional[NS] = None,
    include_extras=False,
):
    try:
        return _type_hints[obj]
    except (KeyError, TypeError):
        types = gth(obj, globalns, localns, include_extras=True)
        if isinstance(obj, _TypedDictMeta) or is_dataclass(NamedTupleMeta):
            try:
                _type_hints[obj] = types
            except TypeError:
                pass
        return types


set_type_hints = get_type_hints

try:  # pragma: no cover
    from typing import _type_repr  # type:ignore
except ImportError:
    # copy from typing._type_repr in case of ...
    def _type_repr(obj):
        if isinstance(obj, type):
            if obj.__module__ == "builtins":
                return obj.__qualname__
            return f"{obj.__module__}.{obj.__qualname__}"
        if obj is ...:
            return "..."
        if isinstance(obj, types.FunctionType):
            return obj.__name__
        return repr(obj)
