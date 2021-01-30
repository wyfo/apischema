import collections.abc
import sys
import typing
from itertools import chain
from types import MappingProxyType
from typing import (
    AbstractSet,
    Any,
    Collection,
    Dict,
    FrozenSet,
    List,
    Mapping,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
)

from apischema.typing import get_origin

AnyType = Any
NoneType: Type[None] = type(None)
Number = Union[int, float]

PRIMITIVE_TYPES = (str, int, bool, float, NoneType)
COLLECTION_TYPES = {
    Collection: tuple,
    collections.abc.Collection: tuple,
    Sequence: tuple,
    collections.abc.Sequence: tuple,
    Tuple: tuple,
    tuple: tuple,
    MutableSequence: list,
    collections.abc.MutableSequence: list,
    List: list,
    list: list,
    AbstractSet: frozenset,
    collections.abc.Set: frozenset,
    FrozenSet: frozenset,
    frozenset: frozenset,
    MutableSet: set,
    collections.abc.MutableSet: set,
    Set: set,
    set: set,
}
MAPPING_TYPES = {
    Mapping: MappingProxyType,
    collections.abc.Mapping: MappingProxyType,
    MutableMapping: dict,
    collections.abc.MutableMapping: dict,
    Dict: dict,
    dict: dict,
    MappingProxyType: MappingProxyType,
}


if (3, 7) <= sys.version_info < (3, 9):  # pragma: no cover

    def subscriptable_origin(tp: AnyType) -> AnyType:
        if (
            type(tp) == type(List[int])  # noqa: E721
            and tp.__module__ == "typing"
            and hasattr(tp, "_name")
        ):
            return getattr(typing, tp._name)
        else:
            return get_origin(tp)


else:  # pragma: no cover
    subscriptable_origin = get_origin  # type: ignore


if sys.version_info >= (3, 7):  # pragma: no cover
    OrderedDict = dict
    ChainMap = collections.ChainMap
else:  # pragma: no cover
    OrderedDict = collections.OrderedDict

    class ChainMap(collections.ChainMap):
        def __iter__(self):
            return iter({k: None for k in chain.from_iterable(reversed(self.maps))})


class Metadata(Mapping[str, Any]):
    def __or__(self, other: Mapping[str, Any]) -> "Metadata":
        return MetadataImplem({**self, **other})

    def __ror__(self, other: Mapping[str, Any]) -> "Metadata":
        return MetadataImplem({**other, **self})


class MetadataMixin(Metadata):
    key: str

    def __getitem__(self, key):
        if key != self.key:
            raise KeyError(key)
        return self

    def __iter__(self):
        return iter((self.key,))

    def __len__(self):
        return 1


class MetadataImplem(dict, Metadata):  # type: ignore
    def __hash__(self):
        return hash(tuple(sorted(self.items())))
