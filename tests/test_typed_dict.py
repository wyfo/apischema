from pytest import raises

from apischema import ValidationError, deserialize, serialize
from apischema.json_schema import deserialization_schema, serialization_schema
from apischema.typing import TypedDict


class TD1(TypedDict, total=False):
    key1: str


class TD2(TypedDict):
    key2: int


class TD3(TD1, TD2, total=False):
    key3: bool


def test_typed_dict():
    assert (
        deserialization_schema(TD3)
        == serialization_schema(TD3)
        == {
            "type": "object",
            "properties": {
                "key1": {"type": "string"},
                "key2": {"type": "integer"},
                "key3": {"type": "boolean"},
            },
            "required": ["key2"],
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
        }
    )
    assert deserialize(TD3, {"Key2": 0, "Key3": True}, aliaser=str.capitalize) == {
        "key2": 0,
        "key3": True,
    }
    with raises(ValidationError):
        assert deserialize(TD3, {})
    assert serialize(TD1, {"key1": ""}) == {"key1": ""}
