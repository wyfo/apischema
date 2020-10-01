import sys
from dataclasses import (  # type: ignore
    Field,
    is_dataclass,
    replace as replace_,
    _FIELDS,
    _FIELD_CLASSVAR,
)
from typing import Mapping, Type, TypeVar

if sys.version_info <= (3, 7):
    is_dataclass_ = is_dataclass

    def is_dataclass(obj) -> bool:
        return is_dataclass_(obj) and getattr(obj, "__origin__", None) is None


T = TypeVar("T")


def replace(__obj: T, **changes) -> T:
    from apischema.fields import FIELDS_SET_ATTR, fields_set, set_fields

    result = replace_(__obj, **changes)
    if hasattr(__obj, FIELDS_SET_ATTR):
        set_fields(result, *fields_set(__obj), *changes, overwrite=True)
    return result


def fields_items(cls: Type) -> Mapping[str, Field]:
    assert is_dataclass(cls)
    return {
        name: field
        for name, field in getattr(cls, _FIELDS).items()
        if field._field_type != _FIELD_CLASSVAR
    }
