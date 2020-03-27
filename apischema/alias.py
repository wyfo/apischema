from dataclasses import fields
from inspect import isfunction
from typing import Callable, TypeVar, overload

from apischema.types import DictWithUnion, Metadata
from apischema.utils import PREFIX

ALIAS_METADATA = f"{PREFIX}alias"
ALIAS_NO_OVERRIDE_METADATA = f"{PREFIX}alias_no_override"

Cls = TypeVar("Cls")


class ClassAliaser:
    def __init__(self, aliaser: Callable[[str], str]):
        self.aliaser = aliaser

    def __call__(self, cls: Cls) -> Cls:
        for field in fields(cls):
            if field.metadata.get(ALIAS_NO_OVERRIDE_METADATA):
                continue
            alias = self.aliaser(field.metadata.get(ALIAS_METADATA, field.name))
            field.metadata = {**field.metadata, ALIAS_METADATA: alias}
        return cls


@overload
def alias(name: str = None, *, override: bool = True) -> Metadata:
    ...


@overload
def alias(aliaser: Callable[[str], str]) -> ClassAliaser:
    ...


def alias(arg=None, *, override: bool = True):  # type: ignore
    if isfunction(arg):
        return ClassAliaser(arg)
    metadata = {}
    if arg is not None:
        metadata[ALIAS_METADATA] = arg
    if not override:
        metadata[ALIAS_NO_OVERRIDE_METADATA] = True
    if not metadata:
        raise ValueError("Alias must be called with arguments")
    return DictWithUnion(metadata)
