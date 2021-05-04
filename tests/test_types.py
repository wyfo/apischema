import sys
from typing import AbstractSet, Dict, List, Mapping, Set

from pytest import mark

from apischema.types import MetadataImplem, MetadataMixin
from apischema.utils import replace_builtins


def test_metadata():
    metadata = MetadataImplem({"a": 0, "b": 1})
    assert metadata | {"b": 2} == {"a": 0, "b": 2}
    assert {"b": 2} | metadata == metadata


class KeyMetadata(MetadataMixin):
    key = "key"


def test_metadata_mixin():
    instance = KeyMetadata()
    assert list(instance.items()) == [("key", instance)]


@mark.parametrize(
    "tp, expected",
    [
        (int, int),
        (List[int], List[int]),
        (Mapping[str, int], Dict[str, int]),
        (AbstractSet[str], Set[str]),
        *(
            [(dict[str, bool], Dict[str, bool])]  # type: ignore
            if sys.version_info >= (3, 9)
            else []
        ),
    ],
)
def test_replace_builtins(tp, expected):
    assert replace_builtins(tp) == expected
