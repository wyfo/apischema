from dataclasses import dataclass
from typing import Annotated

from apischema import schema_ref
from apischema.json_schema import deserialization_schema


# Schema ref can be added as a decorator
@schema_ref("Resource")
@dataclass
class BaseResource:
    id: int
    # or using typing.Annotated
    tags: Annotated[set[str], schema_ref("ResourceTags")]


assert deserialization_schema(BaseResource, all_refs=True) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
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
