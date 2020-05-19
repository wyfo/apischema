from typing import Dict

from apischema.types import AnyType

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


def coerce(cls: AnyType, data):
    if isinstance(data, cls):
        return data
    if cls is bool and isinstance(data, str):
        return STR_TO_BOOL[data]
    return cls(data)


STR_NONE_VALUES = {""}
