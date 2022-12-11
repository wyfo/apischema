from dataclasses import dataclass, field

from apischema import Undefined, UndefinedType, alias, deserialize, serialize
from apischema.fields import with_fields_set
from apischema.json_schema import deserialization_schema
from apischema.metadata import flatten


@dataclass
class JsonSchema:
    title: str | UndefinedType = Undefined
    description: str | UndefinedType = Undefined
    format: str | UndefinedType = Undefined
    ...


@with_fields_set
@dataclass
class RootJsonSchema:
    schema: str | UndefinedType = field(default=Undefined, metadata=alias("$schema"))
    defs: list[JsonSchema] = field(default_factory=list, metadata=alias("$defs"))
    # This field schema is flattened inside the owning one
    json_schema: JsonSchema = field(default_factory=JsonSchema, metadata=flatten)


data = {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "title": "flattened example",
}
root_schema = RootJsonSchema(
    schema="http://json-schema.org/draft/2020-12/schema#",
    json_schema=JsonSchema(title="flattened example"),
)
assert deserialize(RootJsonSchema, data) == root_schema
assert serialize(RootJsonSchema, root_schema) == data
assert deserialization_schema(RootJsonSchema) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "$defs": {
        "JsonSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "format": {"type": "string"},
            },
            "additionalProperties": False,
        }
    },
    # It results in allOf + unevaluatedProperties=False
    "allOf": [
        # RootJsonSchema (without JsonSchema)
        {
            "type": "object",
            "properties": {
                "$schema": {"type": "string"},
                "$defs": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/JsonSchema"},
                    "default": [],
                },
            },
            "additionalProperties": False,
        },
        # JonsSchema
        {"$ref": "#/$defs/JsonSchema"},
    ],
    "unevaluatedProperties": False,
}
