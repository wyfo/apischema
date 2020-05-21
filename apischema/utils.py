from dataclasses import fields, is_dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Generic,
    Hashable,
    Iterable,
    TypeVar,
    Union,
)

PREFIX = "_apischema_"
NO_DEFAULT = object()

Func = TypeVar("Func", bound=Callable)

Hashable_ = TypeVar("Hashable_", bound=Hashable)


def distinct(values: Iterable[Hashable_]) -> Iterable[Hashable_]:
    unique = set()
    for value in values:
        if value not in unique:
            unique.add(value)
            yield value


def to_hashable(data: Union[None, int, float, str, bool, list, dict]) -> Hashable:
    if isinstance(data, list):
        return tuple(map(to_hashable, data))
    if isinstance(data, dict):
        return tuple(sorted((to_hashable(k), to_hashable(v)) for k, v in data.items()))
    return data  # type: ignore


T = TypeVar("T")
U = TypeVar("U")


class GeneratorValue(Iterable[U], Generic[T, U]):
    value: T

    def __init__(self, generator: Generator[U, None, T]):
        self.generator = generator

    def __iter__(self):
        self.value = yield from self.generator


def to_camel_case(s: str):
    pascal_case = "".join(map(str.capitalize, s.split("_")))
    return pascal_case[0].lower() + pascal_case[1:]


def as_dict(obj) -> Dict[str, Any]:
    assert is_dataclass(obj)
    return {f.name: getattr(obj, f.name) for f in fields(obj)}
