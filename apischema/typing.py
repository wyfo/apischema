"""Kind of typing_extensions for this package"""
__all__ = ["get_args", "get_origin", "get_type_hints"]

import sys
from types import ModuleType, new_class
from typing import (  # type: ignore
    Any,
    Callable,
    Collection,
    Dict,
    Generic,
    Set,
    Tuple,
    Type,
    TypeVar,
)


class _FakeType:
    pass


if sys.version_info >= (3, 9):  # pragma: no cover
    from typing import Annotated, TypedDict, get_type_hints, get_origin, get_args
else:  # pragma: no cover
    try:
        from typing_extensions import Annotated, TypedDict
    except ImportError:
        if sys.version_info >= (3, 8):
            from typing import TypedDict
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
            # In Python 3.6: List[Collection[T]][int].__args__ == int != Collection[int]
            if hasattr(tp, "_subs_tree"):
                tp = _assemble_tree(tp._subs_tree())
            if isinstance(tp, _AnnotatedAlias):
                return None if tp.__args__ is None else Annotated
            if tp is Generic:
                return Generic
            return getattr(tp, "__origin__", None)

        def get_args(tp):  # type: ignore
            # In Python 3.6: List[Collection[T]][int].__args__ == int != Collection[int]
            if hasattr(tp, "_subs_tree"):
                tp = _assemble_tree(tp._subs_tree())
            if isinstance(tp, _AnnotatedAlias):
                return () if tp.__args__ is None else (tp.__args__[0], *tp.__metadata__)
            # __args__ can be None in 3.6 inside __set_name__
            res = getattr(tp, "__args__", ()) or ()
            if get_origin(tp) is Callable and res[0] is not Ellipsis:
                res = (list(res[:-1]), res[-1])
            return res


if sys.version_info >= (3, 8):  # pragma: no cover
    from typing import Literal, Protocol  # noqa: F401
else:  # pragma: no cover
    try:
        from typing_extensions import Literal, Protocol  # noqa: F401
    except ImportError:
        pass

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


# sentinel value to avoid to subscript Generic and Protocol
try:
    BASE_GENERIC_MRO = {Generic: Generic, Protocol: Protocol}
except NameError:
    BASE_GENERIC_MRO = {Generic: Generic}


def generic_mro(tp):
    origin = get_origin(tp)
    if origin is None and not hasattr(tp, "__orig_bases__"):
        if not isinstance(tp, type):
            raise TypeError(f"{tp!r} is not a type or a generic alias")
        return tp.__mro__
    result = BASE_GENERIC_MRO.copy()
    _generic_mro(result, tp)
    cls = origin if origin is not None else tp
    return tuple(result.get(sub_cls, sub_cls) for sub_cls in cls.__mro__)


def resolve_type_hints(obj: Any) -> Dict[str, Any]:
    """Wrap get_type_hints to resolve type vars in case of generic inheritance.

    `obj` can also be a parametrized generic class."""
    origin_or_obj = get_origin(obj) or obj
    if isinstance(origin_or_obj, type):
        hints = {}
        for base in reversed(generic_mro(obj)):
            base_origin = get_origin(base) or base
            base_annotations = getattr(base_origin, "__dict__", {}).get(
                "__annotations__", {}
            )
            substitution = dict(
                zip(getattr(base_origin, "__parameters__", ()), get_args(base))
            )
            for name, hint in get_type_hints(base_origin, include_extras=True).items():
                if name not in base_annotations:
                    continue
                if isinstance(hint, TypeVar):
                    hints[name] = substitution.get(hint, hint)
                elif getattr(hint, "__parameters__", ()):
                    hints[name] = hint[
                        tuple(substitution.get(p, p) for p in hint.__parameters__)
                    ]
                else:
                    hints[name] = hint
        return hints
    else:
        return get_type_hints(obj, include_extras=True)


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


def is_new_type(tp: Any) -> bool:
    return hasattr(tp, "__supertype__")


def is_annotated(tp: Any) -> bool:
    try:
        from typing import Annotated  # type: ignore

        return get_origin(tp) == Annotated
    except ImportError:
        try:
            from typing_extensions import Annotated  # type: ignore

            return get_origin(tp) == Annotated
        except ImportError:
            return False


def is_literal(tp: Any) -> bool:
    try:
        from typing import Literal

        return get_origin(tp) == Literal or isinstance(tp, type(Literal))  # py36
    except ImportError:
        try:
            from typing_extensions import Literal  # type: ignore

            return get_origin(tp) == Literal or isinstance(tp, type(Literal))  # py36
        except ImportError:
            return False


def is_named_tuple(tp: Any) -> bool:
    return issubclass(tp, tuple) and hasattr(tp, "_fields")


def is_typed_dict(tp: Any) -> bool:
    try:
        from typing import TypedDict

        return isinstance(tp, type(new_class("_TypedDictImplem", (TypedDict,))))
    except ImportError:
        try:
            from typing_extensions import TypedDict  # type: ignore

            return isinstance(tp, type(new_class("_TypedDictImplem", (TypedDict,))))
        except ImportError:
            return False


def is_type_var(tp: Any) -> bool:
    return isinstance(tp, TypeVar)  # type: ignore


# Don't use sys.version_info because it can also depend of typing_extensions version
def required_keys(typed_dict: Type) -> Collection[str]:
    assert is_typed_dict(typed_dict)
    if hasattr(typed_dict, "__required_keys__"):
        return typed_dict.__required_keys__
    else:
        required: Set[str] = set()
        bases_annotations: Set = set()
        for base in typed_dict.__bases__:
            if not isinstance(base, _TypedDictMeta):
                continue
            bases_annotations.update(base.__annotations__)
            required.update(required_keys(base))
        if typed_dict.__total__:  # type: ignore
            required.update(typed_dict.__annotations__.keys() - bases_annotations)
        return required


# py37/py38 get_origin of builtin wrapped generics return the unsubscriptable builtin
# type.
if (3, 7) <= sys.version_info < (3, 9):
    import typing

    TYPING_ALIASES = {
        getattr(elt, "__origin__", None): elt for elt in typing.__dict__.values()
    }

    def typing_origin(origin: Any) -> Any:
        return TYPING_ALIASES.get(origin, origin)

else:
    typing_origin = lambda tp: tp


def is_type(tp: Any) -> bool:
    """isinstance is not enough because in py39: isinstance(list[int], type) == True"""
    return isinstance(tp, type) and not get_args(tp)
