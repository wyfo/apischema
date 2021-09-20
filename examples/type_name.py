from dataclasses import dataclass
from typing import Annotated

from apischema import type_name
from apischema.json_schema import deserialization_schema


# Type name can be added as a decorator
@type_name("Resource")
@dataclass
class BaseResource:
    id: int
    # or using typing.Annotated
    tags: Annotated[set[str], type_name("ResourceTags")]


assert deserialization_schema(BaseResource, all_refs=True) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "$defs": {
        "Resource": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "tags": {"$ref": "#/$defs/ResourceTags"},
            },
            "required": ["id", "tags"],
            "additionalProperties": False,
        },
        "ResourceTags": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
        },
    },
    "$ref": "#/$defs/Resource",
}
