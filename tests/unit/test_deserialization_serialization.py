from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    AbstractSet,
    Any,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)
from uuid import UUID, uuid4

import pytest

from apischema import schema
from apischema.deserialization import deserialize
from apischema.fields import with_fields_set
from apischema.metadata import properties
from apischema.serialization import serialize
from apischema.typing import Literal
from apischema.validation.errors import ValidationError

uuid = str(uuid4())


def bijection(cls, data, expected):
    obj = deserialize(cls, data)
    assert obj == expected
    assert type(obj) is type(expected)
    assert serialize(cls, obj) == data


def error(data, cls):
    with pytest.raises(ValidationError):
        deserialize(cls, data)


@dataclass(unsafe_hash=True)
class SimpleDataclass:
    a: int


class SimpleEnum(Enum):
    a = "a"


@with_fields_set
@dataclass
class Dataclass:
    nested: SimpleDataclass
    opt: Optional[int] = field(default=None, metadata=schema(min=100))


@pytest.mark.parametrize("data", ["", 0])
def test_any(data):
    bijection(Any, data, data)


@pytest.mark.parametrize(
    "data, expected", [(None, None), ({"a": 0}, SimpleDataclass(0))]
)
def test_optional(data, expected):
    bijection(Optional[SimpleDataclass], data, expected)


def test_optional_error():
    error(0, Optional[str])


@pytest.mark.parametrize("data, expected", [("", ""), ({"a": 0}, SimpleDataclass(0))])
def test_union(data, expected):
    bijection(Union[str, SimpleDataclass], data, expected)


@pytest.mark.parametrize("data", [0, None])
def test_union_error(data):
    error(data, Union[str, SimpleDataclass])


@pytest.mark.parametrize("cls, data", [(int, 0), (str, ""), (bool, True), (float, 0.0)])
def test_primitive(cls, data):
    bijection(cls, data, data)


@pytest.mark.parametrize("data", ["", None])
def test_primitive_error(data):
    error(data, int)


# noinspection PyTypeChecker
@pytest.mark.parametrize(
    "cls, expected",
    [
        (List, [0, SimpleDataclass(0)]),
        (Set, {0, SimpleDataclass(0)}),
        (Sequence, [0, SimpleDataclass(0)]),
        (AbstractSet, {0, SimpleDataclass(0)}),
        (FrozenSet, frozenset([0, SimpleDataclass(0)])),
    ],
)
def test_collection(cls, expected):
    data = [0, {"a": 0}]
    bijection(cls[Union[int, SimpleDataclass]], data, expected)


def test_collection_tuple():
    data = [0, {"a": 0}]
    expected = (0, SimpleDataclass(0))
    bijection(Tuple[2 * (Union[int, SimpleDataclass],)], data, expected)


def test_collection_tuple_variadic():
    data = [0, {"a": 0}]
    expected = (0, SimpleDataclass(0))
    bijection(Tuple[Union[int, SimpleDataclass], ...], data, expected)


@pytest.mark.parametrize("data", [{}, ["", 0]])
def test_iterable_error(data):
    error(data, List[str])


@pytest.mark.parametrize(
    "key_cls, data, expected",
    [
        (str, {"int": 0, "SC": {"a": 0}}, {"int": 0, "SC": SimpleDataclass(0)}),
        (UUID, {uuid: 0}, {UUID(uuid): 0}),
        (UUID, {uuid: 0}, {UUID(uuid): 0}),
    ],
)
def test_mapping(key_cls, data, expected):
    bijection(Mapping[key_cls, Union[int, SimpleDataclass]], data, expected)


@pytest.mark.parametrize("data", [[], {"key": ""}])
def test_mapping_error(data):
    error(data, Mapping[str, int])


@pytest.mark.parametrize("expected", [UUID(uuid), UUID(uuid)])
def test_model(expected):
    bijection(UUID, uuid, expected)


@pytest.mark.parametrize("data", [0, "fake"])
def test_model_error(data):
    error(data, UUID)


def test_enum():
    bijection(SimpleEnum, "a", SimpleEnum.a)


def test_enum_errors():
    error("b", SimpleEnum)


@pytest.mark.parametrize("data", [0, "ok"])
def test_literal(data):
    bijection(Literal[0, "ok"], data, data)


def test_literal_error():
    error(1, Literal[0, "ok"])


@pytest.mark.parametrize(
    "data, expected",
    [
        ({"nested": {"a": 0}}, Dataclass(SimpleDataclass(0), None)),
        ({"nested": {"a": 0}, "opt": None}, Dataclass(SimpleDataclass(0), None)),
        ({"nested": {"a": 0}, "opt": 100}, Dataclass(SimpleDataclass(0), 100)),
    ],
)
def test_dataclass(data, expected):
    bijection(Dataclass, data, expected)


@pytest.mark.parametrize("data", [{}, {"nested": {}, "opt": 1}])
def test_dataclass_error(data):
    error(data, Dataclass)


def test_with_class_context():
    @schema(min=100)
    class BigInt(int):
        pass

    bijection(BigInt, 100, BigInt(100))


def test_properties():
    @dataclass
    class Test:
        startswith_a: Mapping[str, Any] = field(metadata=properties("^a.*$"))
        others: Mapping[str, Any] = field(metadata=properties)

    assert deserialize(Test, {"plop": 0, "allo": 1}) == Test({"allo": 1}, {"plop": 0})


def test_deque():
    bijection(deque, [0, 1], deque([0, 1]))
