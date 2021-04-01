from collections import ChainMap
from dataclasses import fields
from typing import Any, Callable, Dict, TypeVar, overload

from apischema.types import Metadata, MetadataImplem

Aliaser = Callable[[str], str]
Cls = TypeVar("Cls")


class AliasedStr(str):
    pass


@overload
def alias(alias_: str, *, override: bool = True) -> Metadata:
    ...


@overload
def alias(override: bool) -> Metadata:
    ...


@overload
def alias(aliaser: Aliaser) -> Callable[[Cls], Cls]:
    ...


def alias(arg=None, *, override: bool = True):  # type: ignore
    """Field alias or class aliaser

    :param alias_: alias of the field
    :param override: alias can be overridden by a class aliaser
    :param aliaser: compute alias for each (overridable) field of the class decorated
    """
    from apischema.metadata.keys import (
        ALIAS_METADATA,
        ALIAS_NO_OVERRIDE_METADATA,
        is_aggregate_field,
    )

    if callable(arg):

        def aliaser(cls: Cls) -> Cls:
            for field in fields(cls):
                if is_aggregate_field(field) or field.metadata.get(
                    ALIAS_NO_OVERRIDE_METADATA
                ):
                    continue
                alias = arg(field.metadata.get(ALIAS_METADATA, field.name))
                field.metadata = ChainMap({ALIAS_METADATA: alias}, field.metadata)
            return cls

        return aliaser
    metadata: Dict[str, Any] = {}
    if arg is not None:
        metadata[ALIAS_METADATA] = AliasedStr(arg)
    if not override:
        metadata[ALIAS_NO_OVERRIDE_METADATA] = True
    if not metadata:  # pragma: no cover
        raise ValueError("Alias must be called with arguments")
    return MetadataImplem(metadata)


def _global_aliaser(s: str) -> str:
    return s
