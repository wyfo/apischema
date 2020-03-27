from enum import Enum
from itertools import chain
from typing import Dict, Iterable, Tuple, Type, TypeVar

from apischema.data.from_data import DataWithConstraint, FromData
from apischema.data.utils import override_data

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
        STR_TO_BOOL[s] = value
        STR_TO_BOOL[s.capitalize()] = value
        STR_TO_BOOL[s.upper()] = value

STR_NONE_VALUES = set(chain.from_iterable(
    (s, s.capitalize(), s.upper()) for s in ("", "null", "none", "nil")
))


class FromStringified(FromData):
    def primitive(self, cls, data2: DataWithConstraint):
        data, constraint = data2
        if not isinstance(data, str):
            raise ValueError("stringified values must be string")
        if cls is type(None) and data in STR_NONE_VALUES:  # type: ignore # noqa
            return None
        if cls is bool and data in STR_TO_BOOL:
            return STR_TO_BOOL[data]
        try:
            return cls(data)
        except ValueError:
            return super().primitive(cls, data2)

    def enum(self, cls: Type[Enum], data2: DataWithConstraint):
        data, constraint = data2
        data = self.primitive(type(data), (data, None))
        return super().enum(cls, (data, constraint))


T = TypeVar("T")


def from_stringified(items: Iterable[Tuple[str, str]], cls: Type[T], *,
                     additional_properties: bool = False,
                     separator: str = ".") -> T:
    data = None
    for key, value in items:
        if not key:
            raise ValueError("empty keys are not handled")
        try:
            data = override_data(data, key, value, separator)
        except ValueError:
            raise ValueError(f"invalid key '{key}'")
    visitor = FromStringified(additional_properties)
    return visitor.visit(cls, (data, None))
