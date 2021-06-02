from typing import Callable, Dict, TypeVar, overload

from apischema.types import Metadata, MetadataImplem
from apischema.utils import type_dict_wrapper

Aliaser = Callable[[str], str]
Cls = TypeVar("Cls", bound=type)

_class_aliasers: Dict[type, Aliaser] = type_dict_wrapper({})

get_class_aliaser = _class_aliasers.get


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
    from apischema.metadata.keys import ALIAS_METADATA, ALIAS_NO_OVERRIDE_METADATA

    if callable(arg):

        def aliaser(cls: Cls) -> Cls:
            _class_aliasers[cls] = arg
            return cls

        return aliaser
    else:
        metadata = MetadataImplem()
        if arg is not None:
            metadata[ALIAS_METADATA] = arg
        if not override:
            metadata[ALIAS_NO_OVERRIDE_METADATA] = True
        if not metadata:
            raise NotImplementedError
        return metadata


def _global_aliaser(s: str) -> str:
    return s
