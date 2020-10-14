from collections.abc import Set
from dataclasses import dataclass
from typing import NewType

from apischema import schema_ref
from apischema.json_schema import deserialization_schema

Tags = NewType("Tags", Set[str])
schema_ref(...)(Tags)


@dataclass
class Resource:
    id: int
    tags: Tags


assert deserialization_schema(Resource, all_refs=True) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$defs": {
        "Resource": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "tags": {"$ref": "#/$defs/Tags"}},
            "required": ["id", "tags"],
            "additionalProperties": False,
        },
        "Tags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
    "$ref": "#/$defs/Resource",
}
