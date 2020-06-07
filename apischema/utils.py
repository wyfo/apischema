from contextlib import suppress
from dataclasses import Field, MISSING, fields, is_dataclass
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
from apischema.typing import get_type_hints

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


def type_hints_cache(obj):
    try:
        return _type_hints[obj]
    except (KeyError, TypeError):
        types = get_type_hints(obj, include_extras=True)
        with suppress(TypeError):
            _type_hints[obj] = types
        return types


def get_default(field: Field) -> Any:
    if field.default_factory is not MISSING:  # type: ignore
        return field.default_factory()  # type: ignore
    if field.default is not MISSING:
        return field.default
    raise NotImplementedError()


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
