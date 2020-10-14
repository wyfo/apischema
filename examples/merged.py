from dataclasses import dataclass, field
from typing import Optional

from apischema import alias, deserialize, serialize
from apischema.fields import with_fields_set
from apischema.json_schema import deserialization_schema
from apischema.metadata import merged


@with_fields_set
@dataclass
class JsonSchema:
    title: Optional[str] = None
    description: Optional[str] = None
    format: Optional[str] = None
    ...


@with_fields_set
@dataclass
class RootJsonSchema:
    schema: Optional[str] = field(default=None, metadata=alias("$schema"))
    defs: list[JsonSchema] = field(default_factory=list, metadata=alias("$defs"))
    json_schema: JsonSchema = field(default=JsonSchema(), metadata=merged)


data = {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "title": "merged example",
}
root_schema = RootJsonSchema(
    schema="http://json-schema.org/draft/2019-09/schema#",
    json_schema=JsonSchema(title="merged example"),
)
assert deserialize(RootJsonSchema, data) == root_schema
assert serialize(root_schema) == data
assert deserialization_schema(RootJsonSchema) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$defs": {
        "JsonSchema": {
            "type": "object",
            "properties": {
                "title": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "format": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        }
    },
    "type": "object",
    "allOf": [
        {
            "type": "object",
            "properties": {
                "$schema": {"type": ["string", "null"]},
                "$defs": {"type": "array", "items": {"$ref": "#/$defs/JsonSchema"}},
            },
            "additionalProperties": False,
        },
        {"$ref": "#/$defs/JsonSchema"},
    ],
    "unevaluatedProperties": False,
}
