from dataclasses import dataclass, field
from enum import Enum
from typing import List, NewType
from uuid import UUID, uuid4

from pytest import raises

from apischema import (ValidationError, build_input_schema, build_output_schema,
                       from_data, schema, to_data)

Tag = NewType("Tag", str)
schema(title="resource tag", max_len=64)(Tag)


class ResourceType(Enum):
    RESOURCE_A = "A"
    RESOURCE_B = "B"


@dataclass
class Resource:
    id: UUID
    type: ResourceType
    tags: List[Tag] = field(default_factory=list,
                            metadata=schema(max_items=5, unique=True))


def test_resource():
    uuid = uuid4()
    data = {
        "id":   str(uuid),
        "type": "A",
        "tags": ["tag1"]
    }
    resource = from_data(Resource, data)
    assert resource == Resource(uuid, ResourceType.RESOURCE_A, [Tag("tag1")])
    assert to_data(resource) == data
    json_schema = build_input_schema(Resource)
    assert json_schema == build_output_schema(Resource)
    assert to_data(json_schema) == {
        "type":                 "object",
        "required":             ["id", "type"],
        "additionalProperties": False,
        "properties":           {
            "id":   {
                "type":   "string",
                "format": "uuid",
            },
            "type": {
                "type": "string",
                "enum": ["A", "B"],
            },
            "tags": {
                "type":        "array",
                "maxItems":    5,
                "uniqueItems": True,
                "items":       {
                    "type":      "string",
                    "title":     "resource tag",
                    "maxLength": 64,
                },
            },
        }
    }


def test_resource_error():
    with raises(ValidationError) as err:
        from_data(Resource, {"id": "uuid", "type": None, "tags": ["a", "a"]})
    assert err.value == ValidationError(children={
        "id":   ValidationError([
            "[ValueError]badly formed hexadecimal UUID string"
        ]),
        "type": ValidationError([
            "None is not a valid ResourceType"
        ]),
        "tags": ValidationError([
            "duplicates items in ['a', 'a'] (uniqueItems)"
        ])
    })
