from dataclasses import is_dataclass
from typing import Collection, Set, Type, TypeVar

from apischema.dataclass_utils import dataclass_types_and_fields
from apischema.metadata.keys import MERGED_METADATA

_interfaces: Set[Type] = set()

Cls = TypeVar("Cls", bound=Type)


def interface(cls: Cls) -> Cls:
    _interfaces.add(cls)
    return cls


def is_interface(cls: Type) -> bool:
    return cls in _interfaces


def get_interfaces(cls: Type) -> Collection[Type]:
    result = set(filter(is_interface, cls.__mro__[1:]))
    if is_dataclass(cls):
        types, fields, init_vars = dataclass_types_and_fields(cls)  # type: ignore
        for field in fields:
            if MERGED_METADATA in field.metadata:
                merged_cls = types[field.name]
                if is_interface(merged_cls):
                    result.add(merged_cls)
                result.update(get_interfaces(merged_cls))
    return result
