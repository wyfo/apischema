from typing import Collection, Set, Type, TypeVar

_interfaces: Set[Type] = set()

Cls = TypeVar("Cls", bound=Type)


def interface(cls: Cls) -> Cls:
    _interfaces.add(cls)
    return cls


def is_interface(cls: Type) -> bool:
    return cls in _interfaces


def get_interfaces(cls: Type) -> Collection[Type]:
    return list(filter(is_interface, cls.__mro__[1:]))
