from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union

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
    try:
        if isinstance(data, cls):
            return data
        if data is None and cls is not NoneType:
            raise ValueError
        if cls is bool and isinstance(data, str):
            return STR_TO_BOOL[data.lower()]  # type: ignore
        if cls is NoneType and data in STR_NONE_VALUES:
            return None  # type: ignore
        if cls is list and isinstance(data, str):
            raise ValueError
        return cls(data)  # type: ignore
    except (ValueError, TypeError, KeyError):
        raise bad_type(data, cls)


_coercer: Coercer = coerce

Coerce = Union[bool, Coercer]


def wrap_coercer(coercer: Coercer) -> Coercer:
    @wraps(coercer)
    def wrapper(cls, data):
        try:
            result = coercer(cls, data)
        except AssertionError:
            raise
        except Exception:
            raise bad_type(data, cls)
        if not isinstance(result, cls):
            raise bad_type(data, cls)
        return result

    return wrapper


def get_coercer(coerce: Coerce) -> Optional[Coercer]:
    if callable(coerce):
        return wrap_coercer(coerce)
    elif coerce:
        return _coercer
    else:
        return None
