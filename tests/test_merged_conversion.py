from dataclasses import dataclass, field

from graphql import graphql_sync, print_schema
from pytest import raises

from apischema import deserialize, serialize
from apischema.graphql import graphql_schema
from apischema.json_schema import deserialization_schema, serialization_schema
from apischema.metadata import conversion, merged
from apischema.objects import ObjectField, set_object_fields


class Field:
    def __init__(self, attr: int):
        self.attr = attr


set_object_fields(Field, [ObjectField("attr", int)])


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
    return Data(Field(0))


def test_merged_dataclass_model():
    data = deserialize(Data, {"attr": 0})
    assert isinstance(data.data_field, Field) and data.data_field.attr == 0
    assert serialize(Data, data) == {"attr": 0}
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
    schema = graphql_schema(query=[get_data])
    assert graphql_sync(schema, "{getData{attr}}").data == {"getData": {"attr": 0}}
    assert (
        print_schema(schema)
        == """\
type Query {
  getData: Data!
}

type Data {
  attr: Int!
}
"""
    )


class Field2:
    def __init__(self, attr: int):
        self.attr = attr

    @staticmethod
    def from_field(field: Field) -> "Field2":
        return Field2(field.attr)

    def to_field(self) -> Field:
        return Field(self.attr)

    @staticmethod
    def from_int(i: int) -> "Field2":
        return Field2(i)

    def to_int(self) -> int:
        return self.attr


@dataclass
class Data2:
    data_field2: Field2 = field(
        metadata=merged | conversion(Field2.from_field, Field2.to_field)
    )


def get_data2() -> Data2:
    return Data2(Field2(0))


def test_merged_converted():
    data2 = deserialize(Data2, {"attr": 0})
    assert isinstance(data2.data_field2, Field2) and data2.data_field2.attr == 0
    assert serialize(Data2, data2) == {"attr": 0}
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
    schema = graphql_schema(query=[get_data2])
    assert graphql_sync(schema, "{getData2{attr}}").data == {"getData2": {"attr": 0}}
    assert (
        print_schema(schema)
        == """\
type Query {
  getData2: Data2!
}

type Data2 {
  attr: Int!
}
"""
    )


@dataclass
class Data3:
    data_field2: Field2 = field(
        metadata=merged | conversion(Field2.from_int, Field2.to_int)
    )


def get_data3() -> Data3:
    ...


def test_merged_converted_error():
    with raises(TypeError):
        deserialize(Data3, {"attr": 0})
    with raises(TypeError):
        serialize(Data3, Data3(Field2(0)))
    with raises(TypeError):
        deserialization_schema(Data3)
    with raises(TypeError):
        serialization_schema(Data3)
    with raises(TypeError):
        graphql_schema(query=[get_data3])
