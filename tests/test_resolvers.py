from dataclasses import dataclass, field

from apischema import serialize, serialized
from apischema.json_schema import serialization_schema
from apischema.metadata import merged


@dataclass
class Base:
    @serialized
    def serialized(self) -> int:
        return 0


base_schema = {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"serialized": {"readOnly": True, "type": "integer"}},
    "required": ["serialized"],
    "additionalProperties": False,
}


@dataclass
class Inherited(Base):
    pass


@dataclass
class InheritedOverriden(Base):
    def serialized(self) -> int:
        return 1


def test_inherited_serialized():
    assert (
        serialization_schema(Base)
        == serialization_schema(Inherited)
        == serialization_schema(InheritedOverriden)
        == base_schema
    )
    assert serialize(Base()) == serialize(Inherited()) == {"serialized": 0}
    assert serialize(InheritedOverriden()) == {"serialized": 1}


class WithMerged(Base):
    base: Base = field(metadata=merged)


def test_merged_serialized():
    assert serialization_schema(Base) == serialization_schema(WithMerged) == base_schema
    assert serialize(Base()) == serialize(WithMerged()) == {"serialized": 0}
