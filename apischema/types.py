from dataclasses import fields, is_dataclass
from typing import Type, get_type_hints

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
