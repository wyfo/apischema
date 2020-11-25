from enum import Enum, auto
from functools import wraps
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
    cast,
)

from apischema.types import AnyType

PREFIX = "_apischema_"


# Singleton type, see https://www.python.org/dev/peps/pep-0484/#id30
class UndefinedType(Enum):
    def __repr__(self):
        return "Undefined"

    def __str__(self):
        return "Undefined"

    def __bool__(self):
        return False

    Undefined = auto()


Undefined = UndefinedType.Undefined


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


def is_type_var(cls: AnyType) -> bool:
    return isinstance(cls, TypeVar)  # type: ignore


def map_values(mapper: Callable[[V], T], mapping: Mapping[K, V]) -> Mapping[K, T]:
    return {k: mapper(v) for k, v in mapping.items()}


Func = TypeVar("Func", bound=Callable)


def typed_wraps(wrapped: Func) -> Callable[[Callable], Func]:
    return cast(Func, wraps(wrapped))
