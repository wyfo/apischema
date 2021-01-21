import sys
from typing import AbstractSet, Dict, List, Mapping, Set

from pytest import mark

from apischema.types import MappingWithUnion, MetadataMixin, subscriptable_origin
from apischema.utils import replace_builtins


def test_metadata():
    metadata = MappingWithUnion({"a": 0, "b": 1})
    assert metadata | {"b": 2} == {"a": 0, "b": 2}
    assert {"b": 2} | metadata == metadata


class KeyMetadata(MetadataMixin):
    key = "key"


def test_metadata_mixin():
    instance = KeyMetadata()
    assert list(instance.items()) == [("key", instance)]


LIST = subscriptable_origin(List[None])
SET = subscriptable_origin(Set[None])
DICT = subscriptable_origin(Dict[None, None])


@mark.parametrize(
    "tp, expected",
    [
        (int, int),
        (List[int], LIST[int]),
        (Mapping[str, int], DICT[str, int]),
        (AbstractSet[str], SET[str]),
        *(
            [(dict[str, bool], DICT[str, bool])]  # type: ignore
            if sys.version_info >= (3, 9)
            else []
        ),
    ],
)
def test_replace_builtins(tp, expected):
    assert replace_builtins(tp) == expected
