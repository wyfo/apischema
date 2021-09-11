from typing import Any, Callable, Dict, Type, TypeVar, Union

from apischema.json_schema.types import bad_type
from apischema.types import NoneType

T = TypeVar("T")

Coercer = Callable[[Type[T], Any], T]

_bool_pairs = (
    ("0", "1"),
    ("f", "t"),
    ("n", "y"),
    ("no", "yes"),
    ("false", "true"),
    ("off", "on"),
    ("ko", "ok"),
)
STR_TO_BOOL: Dict[str, bool] = {}
for false, true in _bool_pairs:
    for s, value in ((false, False), (true, True)):
        STR_TO_BOOL[s.lower()] = value
STR_NONE_VALUES = {""}


def coerce(cls: Type[T], data: Any) -> T:
    if cls is NoneType:
        if data is None or data in STR_NONE_VALUES:
            return None  # type: ignore
        else:
            raise bad_type(data, cls)
    elif isinstance(data, cls):
        return data
    elif cls is bool:
        if isinstance(data, str):
            return STR_TO_BOOL[data.lower()]  # type: ignore
        elif isinstance(data, int):
            return bool(data)  # type: ignore
        else:
            raise bad_type(data, cls)
    elif cls in (int, float):
        try:
            return cls(data)  # type: ignore
        except ValueError:
            raise bad_type(data, cls)
    elif cls is str:
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            return str(data)  # type: ignore
        else:
            raise bad_type(data, cls)
    else:
        raise bad_type(data, cls)


Coerce = Union[bool, Coercer]
