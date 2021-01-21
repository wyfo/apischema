from functools import wraps
from typing import Any, Callable, Dict, Type, TypeVar, Union

from apischema.json_schema.types import JsonType
from apischema.types import NoneType
from apischema.validation.errors import ValidationError

T = TypeVar("T")

Coercer = Callable[[Type[T], Any], T]


def no_coercion(expected: Type[T], data: Any) -> T:
    if not isinstance(data, expected):
        if expected is float and isinstance(data, int):
            return float(data)  # type: ignore
        msg = (
            f"expected type {JsonType.from_type(expected)},"
            f" found {JsonType.from_type(type(data))}"
        )
        raise ValidationError([msg])
    return data


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


def coercion_error(cls: Type, data) -> ValidationError:
    msg = (
        f"cannot coerce {JsonType.from_type(cls)}"
        f" from {JsonType.from_type(type(data))}"
    )
    return ValidationError([msg])


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
        raise coercion_error(cls, data) from None


_coercer: Coercer = coerce

Coercion = Union[bool, Coercer]


def wrap_coercer(coercer: Coercer) -> Coercer:
    @wraps(coercer)
    def wrapper(cls, data):
        try:
            result = coercer(cls, data)
        except AssertionError:
            raise
        except Exception:
            raise coercion_error(cls, data)
        if not isinstance(result, cls):
            raise coercion_error(cls, data)
        return result

    return wrapper


def get_coercer(coercion: Coercion) -> Coercer:
    if callable(coercion):
        return wrap_coercer(coercion)
    elif coercion:
        return _coercer
    else:
        return no_coercion
