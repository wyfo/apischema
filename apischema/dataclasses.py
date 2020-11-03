from dataclasses import *  # noqa
from typing import TypeVar

T = TypeVar("T")


def replace(__obj: T, **changes) -> T:  # type: ignore
    from apischema.fields import FIELDS_SET_ATTR, fields_set, set_fields
    from dataclasses import replace as replace_

    result = replace_(__obj, **changes)
    if hasattr(__obj, FIELDS_SET_ATTR):
        set_fields(result, *fields_set(__obj), *changes, overwrite=True)
    return result


del TypeVar, T
