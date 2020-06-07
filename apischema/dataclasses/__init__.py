import sys
from dataclasses import is_dataclass, replace as replace_

if sys.version_info <= (3, 7):
    is_dataclass_ = is_dataclass

    def is_dataclass(obj) -> bool:
        return is_dataclass_(obj) and getattr(obj, "__origin__", None) is None


def replace(*args, **changes):
    from apischema.fields import FIELDS_SET_ATTR, fields_set, set_fields

    result = replace_(*args, **changes)
    obj = args[0]
    if hasattr(obj, FIELDS_SET_ATTR):
        set_fields(result, *fields_set(obj), *changes, overwrite=True)
    return result
