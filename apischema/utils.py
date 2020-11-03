from dataclasses import fields, is_dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.types import AnyType
from apischema.typing import get_args

PREFIX = "_apischema_"
Nil = object()


def is_hashable(obj) -> bool:
    try:
        hash(obj)
    except Exception:  # should be TypeError, but who knows what can happen
        return False
    else:
        return True


def to_hashable(data: Union[None, int, float, str, bool, list, dict]) -> Hashable:
    if isinstance(data, list):
        return tuple(map(to_hashable, data))
    if isinstance(data, dict):
        return tuple(sorted((to_hashable(k), to_hashable(v)) for k, v in data.items()))
    return data  # type: ignore


def to_camel_case(s: str):
    pascal_case = "".join(map(str.capitalize, s.split("_")))
    return pascal_case[0].lower() + pascal_case[1:]


def as_dict(obj) -> Dict[str, Any]:
    """like dataclasses.asdict but without deepcopy"""
    assert is_dataclass(obj)
    return {f.name: getattr(obj, f.name) for f in fields(obj)}


_type_hints: Dict[str, Mapping[str, Type]] = {}


def type_name(cls: AnyType) -> str:
    for attr in ("__name__", "name", "_name"):
        if hasattr(cls, attr):
            return getattr(cls, attr)
    return str(cls)


MakeDataclassField = Union[Tuple[str, AnyType], Tuple[str, AnyType, Any]]

T = TypeVar("T")


def merge_opts(
    func: Callable[[T, T], T]
) -> Callable[[Optional[T], Optional[T]], Optional[T]]:
    def wrapper(opt1, opt2):
        if opt1 is None:
            return opt2
        if opt2 is None:
            return opt1
        return func(opt1, opt2)

    return wrapper


K = TypeVar("K")
V = TypeVar("V")


@merge_opts
def merge_opts_mapping(m1: Mapping[K, V], m2: Mapping[K, V]) -> Mapping[K, V]:
    return {**m1, **m2}


def has_free_type_vars(cls: AnyType):
    return (
        isinstance(cls, TypeVar)  # type: ignore
        or getattr(cls, "__parameters__", ())
        or any(has_free_type_vars(arg) for arg in get_args(cls))
    )
