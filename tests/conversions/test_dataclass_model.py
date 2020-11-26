from dataclasses import dataclass, field, make_dataclass
from typing import Type

from apischema import alias, deserialize, serialize
from apischema.conversions.dataclass_model import dataclass_model
from apischema.json_schema import deserialization_schema


class Simple:
    def __init__(self, a: int):
        self.a = a

    def __eq__(self, other):
        return type(other) == Simple and other.a == self.a


@dataclass_model(Simple)
@dataclass
class SimpleModel:
    a: int


@dataclass_model(Simple, extra=True)
@dataclass
class SimpleModel2:
    a: int = field(metadata=alias("b"))


def test_simple_dataclass_model():
    assert deserialize(Simple, {"a": 0}) == Simple(0)
    assert serialize(Simple(0)) == {"a": 0}
    assert deserialization_schema(Simple) == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
    }


class Lazy:
    def __init__(self, a: int):
        self.a = a

    def __eq__(self, other):
        return type(other) == Lazy and other.a == self.a


@dataclass_model(Lazy)
def lazy_model() -> Type:
    return make_dataclass("LazyModel", [("a", int)])


@dataclass_model(Lazy, extra=True)
def lazy_model2() -> Type:
    return make_dataclass("LazyModel", [("a", int, field(metadata=alias("b")))])


def test_lazy_dataclass_model():
    assert deserialize(Lazy, {"a": 0}) == Lazy(0)
    assert serialize(Lazy(0)) == {"a": 0}
    assert deserialization_schema(Lazy) == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
    }


def test_dataclass_model_conversions_selection():
    assert deserialize(Simple, {"b": 0}, conversions={Simple: SimpleModel2}) == Simple(
        0
    )
    assert serialize(Simple(0), conversions={Simple: SimpleModel2}) == {"b": 0}
    assert deserialize(Lazy, {"b": 0}, conversions={Lazy: lazy_model2}) == Lazy(0)
    assert serialize(Lazy(0), conversions={Lazy: lazy_model2}) == {"b": 0}
