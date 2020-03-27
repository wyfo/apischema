"""Kind of typing_extensions for this package"""
__all__ = [
    "Annotated",
    "Literal",
    "NamedTupleMeta",
    "Protocol",
    "TypedDict",
    "_AnnotatedAlias",
    "_GenericAlias",
    "_TypedDictMeta",
    "get_type_hints",
    "set_type_hints",
    "_type_repr"
]

import sys
import types
from dataclasses import is_dataclass
from inspect import isclass
from typing import (Any, Dict, Generic, Mapping, NamedTuple, Optional, Type, TypeVar)


class NoType:
    pass


NO_TYPE = NoType()

if sys.version_info >= (3, 9):
    from typing import Annotated, get_type_hints as gth
else:
    try:
        from typing_extensions import Annotated, get_type_hints as gth
    except ImportError:
        from typing import get_type_hints as gth_


        def gth(obj, globalns=None, localns=None,  # type: ignore # noqa
                include_extras=False):
            return gth_(obj, globalns, localns)


        class MetaAnnotated(type):
            def __getitem__(self, _):
                return NO_TYPE


        class Annotated(MetaAnnotated):  # type: ignore # noqa
            pass
if sys.version_info >= (3, 8):
    from typing import Literal, Protocol, TypedDict
else:
    try:
        from typing_extensions import Literal, Protocol, TypedDict
    except ImportError:
        Literal = NO_TYPE  # type: ignore
        TypedDict = NO_TYPE  # type: ignore
        Protocol = NO_TYPE  # type: ignore

Annotated = Annotated
Literal = Literal
Protocol = Protocol
TypedDict = TypedDict

_T = TypeVar("_T")
_GenericAlias = type(Generic[_T])
_AnnotatedAlias = type(Annotated[_T, ...])
_TypedDictMeta = type(TypedDict)
NamedTupleMeta = type(NamedTuple)

_type_hints: Dict[str, Mapping[str, Type]] = {}

NS = Dict[str, Any]


def get_type_hints(obj, globalns: Optional[NS] = None,
                   localns: Optional[NS] = None):
    try:
        return _type_hints[obj]
    except (KeyError, TypeError):
        types = gth(obj, globalns, localns, include_extras=True)
        try:
            _type_hints[obj] = types
        except TypeError:
            pass
        if isclass(obj) and is_dataclass(obj):
            from apischema.conversion import resolve_fieds_converters
            resolve_fieds_converters(obj)
        return types


set_type_hints = get_type_hints

try:  # pragma: no cover
    from typing import _type_repr  # type:ignore
except ImportError:
    # copy from typing._type_repr in case of ...
    def _type_repr(obj):
        if isinstance(obj, type):
            if obj.__module__ == 'builtins':
                return obj.__qualname__
            return f'{obj.__module__}.{obj.__qualname__}'
        if obj is ...:
            return ('...')
        if isinstance(obj, types.FunctionType):
            return obj.__name__
        return repr(obj)
