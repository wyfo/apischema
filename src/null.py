from typing import Any, Iterable, TypeVar

NULL_VALUES_FIELD = "__null_values__"

T = TypeVar("T")


def set_null_values(self: T, *fields: str) -> T:
    setattr(self, NULL_VALUES_FIELD, fields)
    return self


def null_values(self: Any) -> Iterable[str]:
    return getattr(self, NULL_VALUES_FIELD, ())
