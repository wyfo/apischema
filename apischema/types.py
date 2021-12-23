import collections.abc
import sys
from enum import Enum, auto
from itertools import chain
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
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

AnyType = Any
NoneType: Type[None] = type(None)
Number = Union[int, float]

PRIMITIVE_TYPES = (str, int, bool, float, NoneType)
COLLECTION_TYPES = (
    Collection,
    collections.abc.Collection,
    Sequence,
    collections.abc.Sequence,
    Tuple,
    tuple,
    MutableSequence,
    collections.abc.MutableSequence,
    List,
    list,
    AbstractSet,
    collections.abc.Set,
    FrozenSet,
    frozenset,
    MutableSet,
    collections.abc.MutableSet,
    Set,
    set,
)
MAPPING_TYPES = (
    Mapping,
    collections.abc.Mapping,
    MutableMapping,
    collections.abc.MutableMapping,
    Dict,
    dict,
    MappingProxyType,
)


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


# Singleton type, see https://www.python.org/dev/peps/pep-0484/#id30
if TYPE_CHECKING:

    class UndefinedType(Enum):
        Undefined = auto()

    Undefined = UndefinedType.Undefined
else:

    class UndefinedType:
        def __new__(cls):
            return Undefined

        def __repr__(self):
            return "Undefined"

        def __str__(self):
            return "Undefined"

        def __bool__(self):
            return False

    Undefined = object.__new__(UndefinedType)
