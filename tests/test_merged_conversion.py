from dataclasses import dataclass, field

from graphql import print_schema
from pytest import raises

from apischema import deserialize, serialize
from apischema.conversions import dataclass_model, extra_deserializer, extra_serializer
from apischema.conversions.metadata import conversions
from apischema.graphql import graphql_schema
from apischema.json_schema import deserialization_schema, serialization_schema
from apischema.metadata import merged


class Field:
    def __init__(self, attr: int):
        self.attr = attr


@dataclass_model(Field)
@dataclass
class FieldModel:
    attr: int


@dataclass
class Data:
    data_field: Field = field(metadata=merged)


json_schema = {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "allOf": [
        {"type": "object", "additionalProperties": False},
        {
            "type": "object",
            "properties": {"attr": {"type": "integer"}},
            "required": ["attr"],
            "additionalProperties": False,
        },
    ],
    "unevaluatedProperties": False,
}
graphql_schema_str = """\
type Query {
  getData: Data
}

type Data {
  attr: Int!
}
"""


def get_data() -> Data:
    ...


def test_merged_dataclass_model():
    data = deserialize(Data, {"attr": 0})
    assert isinstance(data.data_field, Field) and data.data_field.attr == 0
    assert serialize(data) == {"attr": 0}
    assert (
        deserialization_schema(Data)
        == serialization_schema(Data)
        == {
            "$schema": "http://json-schema.org/draft/2019-09/schema#",
            "type": "object",
            "allOf": [
                {"type": "object", "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {"attr": {"type": "integer"}},
                    "required": ["attr"],
                    "additionalProperties": False,
                },
            ],
            "unevaluatedProperties": False,
        }
    )
    assert (
        print_schema(graphql_schema(query=[get_data]))
        == """\
type Query {
  getData: Data
}

type Data {
  attr: Int!
}
"""
    )


class Field2:
    def __init__(self, attr: int):
        self.attr = attr

    @extra_deserializer
    @staticmethod
    def from_field(field: Field) -> "Field2":
        return Field2(field.attr)

    @extra_serializer
    def to_field(self) -> Field:
        return Field(self.attr)

    @extra_deserializer
    @staticmethod
    def from_int(i: int) -> "Field2":
        return Field2(i)

    @extra_serializer
    def to_int(self) -> int:
        return self.attr


@dataclass
class Data2:
    data_field2: Field2 = field(metadata=merged | conversions(Field))


def get_data2() -> Data2:
    ...


def test_merged_converted():
    data2 = deserialize(Data2, {"attr": 0})
    assert isinstance(data2.data_field2, Field2) and data2.data_field2.attr == 0
    assert serialize(data2) == {"attr": 0}
    assert (
        deserialization_schema(Data)
        == serialization_schema(Data)
        == {
            "$schema": "http://json-schema.org/draft/2019-09/schema#",
            "type": "object",
            "allOf": [
                {"type": "object", "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {"attr": {"type": "integer"}},
                    "required": ["attr"],
                    "additionalProperties": False,
                },
            ],
            "unevaluatedProperties": False,
        }
    )
    assert (
        print_schema(graphql_schema(query=[get_data2]))
        == """\
type Query {
  getData2: Data2
}

type Data2 {
  attr: Int!
}
"""
    )


@dataclass
class Data3:
    data_field2: Field2 = field(metadata=merged | conversions(int))


def get_data3() -> Data3:
    ...


def test_merged_converted_error():
    with raises(TypeError):
        deserialize(Data3, {"attr": 0})
    with raises(TypeError):
        serialize(Data3(Field2(0)))
    with raises(TypeError):
        deserialization_schema(Data3)
    with raises(TypeError):
        serialization_schema(Data3)
    with raises(TypeError):
        graphql_schema(query=[get_data3])
