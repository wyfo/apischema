from dataclasses import dataclass
from enum import Enum
from typing import (AbstractSet, Any, Iterable, List, Mapping, Optional,
                    Sequence, Set, Union)
from uuid import UUID as BaseUUID, uuid4

from pytest import mark, raises
from typing_extensions import Literal

from src.data import from_data, to_data
from src.field import field
from src.model import Model
from src.null import null_values
from src.spec import NumSpec, SpecClass
from src.validation import ValidationError
from src.validator import validate


class UUID(BaseUUID, Model[str]):
    pass


uuid = str(uuid4())


def bijection(cls, data, expected, nulls: Optional[Iterable[str]] = None):
    obj = from_data(cls, data)
    assert obj == expected
    assert to_data(cls, obj) == data
    if nulls is not None:
        assert set(null_values(obj)) == set(nulls)


def error(cls, data):
    with raises(ValidationError):
        from_data(cls, data)


@dataclass(unsafe_hash=True)
class SimpleClass:
    a: int


class TestEnum(Enum):
    a = "a"


@dataclass
class TestDataclass:
    nested: SimpleClass
    opt: Optional[int] = field(default=None, spec=NumSpec(min=100))


@dataclass
class PartialValidator:
    a: int = 0
    b: int = 0
    c: int = 0

    @validate("a", "b")
    def validate(self):
        if self.a == self.b:
            yield "error"


@mark.parametrize("data", ["", 0])
def test_any(data):
    bijection(Any, data, data)


@mark.parametrize("data, expected", [
    (None, None),
    ({"a": 0}, SimpleClass(0)),
])
def test_optional(data, expected):
    bijection(Optional[SimpleClass], data, expected)


def test_optional_error():
    error(Optional[str], 0)


@mark.parametrize("data, expected", [
    ("", ""),
    ({"a": 0}, SimpleClass(0))
])
def test_union(data, expected):
    bijection(Union[str, SimpleClass], data, expected)


@mark.parametrize("data", [0, None])
def test_union_error(data):
    error(Union[str, SimpleClass], data)


@mark.parametrize("cls, data", [
    (int, 0),
    (str, ""),
    (bool, True),
    (float, 0.0)
])
def test_primitive(cls, data):
    bijection(cls, data, data)


@mark.parametrize("data", ["", None])
def test_primitive_error(data):
    error(int, data)


# noinspection PyTypeChecker
@mark.parametrize("cls, expected", [
    (List, [0, SimpleClass(0)]),
    (Set, {0, SimpleClass(0)}),
    (Sequence, (0, SimpleClass(0))),
    (AbstractSet, frozenset([0, SimpleClass(0)]))
])
def test_iterable(cls, expected):
    data = [0, {"a": 0}]
    bijection(cls[Union[int, SimpleClass]], data, expected)


@mark.parametrize("data", [{}, ["", 0]])
def test_iterable_error(data):
    error(List[str], data)


@mark.parametrize("key_cls, data, expected", [
    (str, {"int": 0, "SC": {"a": 0}}, {"int": 0, "SC": SimpleClass(0)}),
    (UUID, {uuid: 0}, {UUID(uuid): 0}),
    (UUID, {uuid: 0}, {BaseUUID(uuid): 0}),
])
def test_mapping(key_cls, data, expected):
    bijection(Mapping[key_cls, Union[int, SimpleClass]], data, expected)


@mark.parametrize("data", [
    [],
    {"key": ""},
])
def test_mapping_error(data):
    error(Mapping[str, int], data)


@mark.parametrize("expected", [UUID(uuid), BaseUUID(uuid)])
def test_model(expected):
    bijection(UUID, uuid, expected)


@mark.parametrize("data", [0, "fake"])
def test_model_error(data):
    error(UUID, data)


def test_enum():
    bijection(TestEnum, "a", TestEnum.a)


def test_enum_errors():
    error(TestEnum, "b")


@mark.parametrize("data", [0, "ok"])
def test_literal(data):
    bijection(Literal[0, "ok"], data, data)


def test_literal_error():
    error(Literal[0, "ok"], 1)
    with raises(ValueError):
        to_data(Literal[0, "ok"], 1)


@mark.parametrize("data, expected, nulls", [
    ({"nested": {"a": 0}}, TestDataclass(SimpleClass(0), None), []),
    ({"nested": {"a": 0},
      "opt":    None}, TestDataclass(SimpleClass(0), None), ["opt"]),
    ({"nested": {"a": 0}, "opt": 100}, TestDataclass(SimpleClass(0), 100), []),
])
def test_dataclass(data, expected, nulls):
    bijection(TestDataclass, data, expected, nulls)


def test_dataclass_partial_validator():
    with raises(ValidationError):
        from_data(PartialValidator, {})


@mark.parametrize("data", [{}, {"nested": {}, "opt": 1}])
def test_dataclass_error(data):
    error(TestDataclass, data)


def test_with_class_context():
    class BigInt(SpecClass, Model[int], int):
        min = 100

    bijection(BigInt, 100, 100)
