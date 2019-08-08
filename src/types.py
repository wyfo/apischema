import collections.abc
from dataclasses import fields, is_dataclass
from typing import Type, Union, get_type_hints

PRIMITIVE_TYPES = (str, int, bool, float)

Primitive = Type[Union[str, int, bool, float]]

ITERABLE_TYPES = (collections.abc.Sequence, list,
                  collections.abc.Set, set)

MAPPING_TYPES = (collections.abc.Mapping, dict)


def iterable_type(cls: Type) -> Type:
    assert issubclass(cls, collections.abc.Iterable)
    if cls is list:
        return list
    if cls is collections.abc.Sequence:
        return tuple
    if cls is set:
        return set
    if cls is collections.abc.Set:
        return frozenset
    raise NotImplementedError()


def type_name(cls: Type) -> str:
    for attr in ("__name__", "name", "_name"):
        if hasattr(cls, attr):
            return getattr(cls, attr)
    return str(cls)


TYPES_RESOLVED_FIELD = "__types_resolved__"


def is_resolved(cls: Type):
    assert is_dataclass(cls)
    return hasattr(cls, TYPES_RESOLVED_FIELD)


def resolve_types(cls: Type):
    assert is_dataclass(cls)
    type_hints = get_type_hints(cls)
    # noinspection PyDataclass
    for field in fields(cls):
        field.type = type_hints[field.name]
    setattr(cls, TYPES_RESOLVED_FIELD, True)
