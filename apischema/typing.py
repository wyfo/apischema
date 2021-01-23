"""Kind of typing_extensions for this package"""
__all__ = ["_LiteralMeta", "_TypedDictMeta", "get_args", "get_origin", "get_type_hints"]

import sys
from types import ModuleType
from typing import Any, Callable, Generic, Tuple, TypeVar, _eval_type  # type: ignore


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
            # __args__ can be None in 3.6 inside __set_name__
            res = getattr(tp, "__args__", ()) or ()
            if get_origin(tp) is Callable and res[0] is not Ellipsis:
                res = (list(res[:-1]), res[-1])
            return res


if sys.version_info >= (3, 7):
    from typing import _collect_type_vars, ForwardRef  # type: ignore
else:
    from typing import _type_vars, _ForwardRef

    _collect_type_vars = _type_vars

    def ForwardRef(arg, is_argument):
        return _ForwardRef(arg)


try:
    from typing import _strip_annotations  # type: ignore
except ImportError:
    try:
        from typing_extensions import _strip_annotations  # type: ignore
    except ImportError:

        def _strip_annotations(t):
            return t


def _generic_mro(result, tp):
    origin = get_origin(tp)
    if origin is None:
        origin = tp
    result[origin] = tp
    if hasattr(origin, "__orig_bases__"):
        parameters = _collect_type_vars(origin.__orig_bases__)
        substitution = dict(zip(parameters, get_args(tp)))
        for base in origin.__orig_bases__:
            if get_origin(base) in result:
                continue
            base_parameters = getattr(base, "__parameters__", ())
            if base_parameters:
                base = base[tuple(substitution.get(p, p) for p in base_parameters)]
            _generic_mro(result, base)


def generic_mro(tp):
    origin = get_origin(tp)
    if origin is None and not hasattr(tp, "__orig_bases__"):
        if not isinstance(tp, type):
            raise TypeError(f"{tp!r} is not a type or a generic alias")
        return tp.__mro__
    # sentinel value to avoid to subscript Generic and Protocol
    try:
        result = {Generic: Generic, Protocol: Protocol}
    except NameError:
        result = {Generic: Generic}
    _generic_mro(result, tp)
    cls = origin if origin is not None else tp
    return tuple(result.get(sub_cls, sub_cls) for sub_cls in cls.__mro__)


def _class_annotations(cls, globalns, localns):
    hints = {}
    if globalns is None:
        base_globals = sys.modules[cls.__module__].__dict__
    else:
        base_globals = globalns
    for name, value in cls.__dict__.get("__annotations__", {}).items():
        if value is None:
            value = type(None)
        if isinstance(value, str):
            value = ForwardRef(value, is_argument=False)
        hints[name] = _eval_type(value, base_globals, localns)
    return hints


def get_type_hints2(obj, globalns=None, localns=None):  # type: ignore
    if isinstance(obj, type) or isinstance(get_origin(obj), type):
        hints = {}
        for base in reversed(generic_mro(obj)):
            origin = get_origin(base)
            if hasattr(origin, "__orig_bases__"):
                parameters = _collect_type_vars(origin.__orig_bases__)
                substitution = dict(zip(parameters, get_args(base)))
                annotations = _class_annotations(get_origin(base), globalns, localns)
                for name, tp in annotations.items():
                    if isinstance(tp, TypeVar):
                        hints[name] = substitution.get(tp, tp)
                    elif getattr(tp, "__parameters__", ()):
                        hints[name] = tp[
                            tuple(substitution.get(p, p) for p in tp.__parameters__)
                        ]
                    else:
                        hints[name] = tp
            else:
                hints.update(_class_annotations(base, globalns, localns))
        return hints
    else:
        return get_type_hints(obj, globalns, localns, include_extras=True)


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
