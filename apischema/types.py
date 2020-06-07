import collections.abc
import sys
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
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.typing import Annotated, NO_TYPE

AnyType = Any
NoneType: Type[None] = type(None)
Number = Union[int, float]

PRIMITIVE_TYPES = (str, int, bool, float, NoneType)

if sys.version_info >= (3, 7):  # pragma: no cover
    COLLECTION_TYPES = {
        collections.abc.Collection: tuple,
        collections.abc.Sequence: tuple,
        tuple: tuple,
        collections.abc.MutableSequence: list,
        list: list,
        collections.abc.Set: frozenset,
        frozenset: frozenset,
        collections.abc.MutableSet: set,
        set: set,
    }
    MAPPING_TYPES = {
        collections.abc.Mapping: MappingProxyType,
        collections.abc.MutableMapping: dict,
        dict: dict,
    }
    LIST_TYPE = list
    TUPLE_TYPE = tuple
    DICT_TYPE = dict

else:  # pragma: no cover
    COLLECTION_TYPES = {
        Collection: tuple,
        Sequence: tuple,
        Tuple: tuple,
        MutableSequence: list,
        List: list,
        AbstractSet: frozenset,
        FrozenSet: frozenset,
        Set: set,
    }
    MAPPING_TYPES = {Mapping: MappingProxyType, MutableMapping: dict, Dict: dict}
    LIST_TYPE = List
    TUPLE_TYPE = Tuple
    DICT_TYPE = Dict


if sys.version_info >= (3, 7):  # pragma: no cover
    OrderedDict = dict
else:  # pragma: no cover
    from collections import OrderedDict  # noqa

# Kind of hack to benefit of PEP 584
if sys.version_info >= (3, 9):  # pragma: no cover
    Metadata = Mapping[str, Any]
else:  # pragma: no cover

    class Metadata(Mapping[str, Any]):
        def __or__(self, other: Mapping[str, Any]) -> "Metadata":
            return MappingWithUnion({**self, **other})

        def __ror__(self, other: Mapping[str, Any]) -> "Metadata":
            return MappingWithUnion({**other, **self})


class MetadataMixin(Metadata):
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


if sys.version_info >= (3, 9):
    MappingWithUnion = MappingProxyType
else:

    class MappingWithUnion(dict, Metadata):
        pass


class Skipped(Exception):
    pass


class _Skip:
    def __call__(self, *, schema_only: bool):
        return SkipSchema if schema_only else self


Skip = _Skip()
SkipSchema = object()


T = TypeVar("T")

if Annotated is not NO_TYPE:
    NotNull = Union[T, Annotated[None, Skip]]
else:

    class _NotNull:
        def __getitem__(self, item):
            raise TypeError("NotNull requires Annotated (PEP 593)")

    NotNull = _NotNull()  # type: ignore
