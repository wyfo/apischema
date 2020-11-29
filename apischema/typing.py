"""Kind of typing_extensions for this package"""
__all__ = ["_LiteralMeta", "_TypedDictMeta", "get_args", "get_origin", "get_type_hints"]

import sys
from types import ModuleType
from typing import Any, Callable, Generic, Tuple, TypeVar


class _FakeType:
    pass


if sys.version_info >= (3, 9):  # pragma: no cover
    from typing import Annotated, get_type_hints, get_origin, get_args
else:  # pragma: no cover
    try:
        from typing_extensions import Annotated
    except ImportError:
        pass
    try:
        from typing_extensions import get_type_hints as gth
    except ImportError:
        from typing import get_type_hints as _gth

        def gth(obj, globalns=None, localns=None, include_extras=False):  # type: ignore
            return _gth(obj, globalns, localns)

    def get_type_hints(  # type: ignore
        obj, globalns=None, localns=None, include_extras=False
    ):
        # TODO This has been fixed in recent 3.7 and 3.8
        # fix https://bugs.python.org/issue37838
        if not isinstance(obj, (type, ModuleType)) and globalns is None:
            nsobj = obj
            while hasattr(nsobj, "__wrapped__"):
                nsobj = nsobj.__wrapped__
            globalns = getattr(nsobj, "__globals__", None)
        localns = {"unicode": str, **(localns or {})}
        return gth(obj, globalns, localns, include_extras)

    try:
        from typing_extensions import get_origin, get_args
    except ImportError:

        def _assemble_tree(tree: Tuple[Any]) -> Any:
            if not isinstance(tree, tuple):
                return tree
            else:
                origin, *args = tree  # type: ignore
                if origin is Annotated:
                    return Annotated[(_assemble_tree(args[0]), *args[1])]
                else:
                    return origin[tuple(map(_assemble_tree, args))]

        def get_origin(tp):  # type: ignore
            # In Python 3.6: List[Collection[T]][int]._args__ == int != Collection[int]
            if hasattr(tp, "_subs_tree"):
                tp = _assemble_tree(tp._subs_tree())
            if isinstance(tp, _AnnotatedAlias):
                return Annotated
            if tp is Generic:
                return Generic
            return getattr(tp, "__origin__", None)

        def get_args(tp):  # type: ignore
            # In Python 3.6: List[Collection[T]][int]._args__ == int != Collection[int]
            if hasattr(tp, "_subs_tree"):
                tp = _assemble_tree(tp._subs_tree())
            if isinstance(tp, _AnnotatedAlias):
                return (tp.__args__[0], *tp.__metadata__)
            res = getattr(tp, "__args__", ())
            if get_origin(tp) is Callable and res[0] is not Ellipsis:
                res = (list(res[:-1]), res[-1])
            return res


if sys.version_info >= (3, 8):  # pragma: no cover
    from typing import Literal, TypedDict, Protocol  # noqa: F401
else:  # pragma: no cover
    try:
        from typing_extensions import Literal, TypedDict, Protocol  # noqa: F401
    except ImportError:
        pass


_T = TypeVar("_T")
_GenericAlias: Any = type(Generic[_T])
try:
    _AnnotatedAlias: Any = type(Annotated[_T, ...])
except NameError:
    _AnnotatedAlias = _FakeType
try:

    class _TypedDictImplem(TypedDict):
        pass

    _LiteralMeta: Any = type(Literal)
    _TypedDictMeta: Any = type(_TypedDictImplem)
except NameError:
    _LiteralMeta, _TypedDictMeta = _FakeType, _FakeType  # type: ignore
