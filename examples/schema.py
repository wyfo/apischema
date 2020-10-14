from dataclasses import dataclass, field
from typing import NewType

from apischema import schema
from apischema.json_schema import deserialization_schema

Tag = NewType("Tag", str)
schema(min_len=3, pattern=r"^\w*$", examples=["available", "EMEA"])(Tag)


@dataclass
class Resource:
    id: int
    tags: list[Tag] = field(
        default_factory=list,
        metadata=schema(
            description="regroup multiple resources", max_items=3, unique=True
        ),
    )


assert deserialization_schema(Resource) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "integer"},
        "tags": {
            "description": "regroup multiple resources",
            "items": {
                "examples": ["available", "EMEA"],
                "minLength": 3,
                "pattern": "^\\w*$",
                "type": "string",
            },
            "maxItems": 3,
            "type": "array",
            "uniqueItems": True,
        },
    },
    "required": ["id"],
    "type": "object",
}
