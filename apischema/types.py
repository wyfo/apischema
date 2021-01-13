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

    def subscriptable_origin(cls: AnyType) -> AnyType:
        if (
            type(cls) == type(List[int])  # noqa: E721
            and cls.__module__ == "typing"
            and hasattr(cls, "_name")
        ):
            return getattr(typing, cls._name)
        else:
            return get_origin(cls)


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


class MetadataUnion(Mapping[str, Any]):
    def __or__(self, other: Mapping[str, Any]) -> "Metadata":
        return MappingWithUnion({**self, **other})

    def __ror__(self, other: Mapping[str, Any]) -> "Metadata":
        return MappingWithUnion({**other, **self})


# Kind of hack to benefit of PEP 584
if sys.version_info >= (3, 9):  # pragma: no cover
    Metadata = Mapping[str, Any]
else:  # pragma: no cover
    Metadata = MetadataUnion


class MetadataMixin(MetadataUnion):
    _key: str

    def __init__(self, key: str):
        super().__setattr__("_key", key)

    def __getitem__(self, key):
        if key != self._key:
            raise KeyError(key)
        return self

    def __iter__(self):
        return iter((self._key,))

    def __len__(self):
        return 1


if sys.version_info >= (3, 9):  # pragma: no cover
    MappingWithUnion = MappingProxyType
else:  # pragma: no cover

    class MappingWithUnion(dict, MetadataUnion):
        pass
