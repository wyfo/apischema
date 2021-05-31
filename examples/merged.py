from dataclasses import dataclass, field
from typing import Union

from apischema import Undefined, UndefinedType, alias, deserialize, serialize
from apischema.fields import with_fields_set
from apischema.json_schema import deserialization_schema
from apischema.metadata import merged


@dataclass
class JsonSchema:
    title: Union[str, UndefinedType] = Undefined
    description: Union[str, UndefinedType] = Undefined
    format: Union[str, UndefinedType] = Undefined
    ...


@with_fields_set
@dataclass
class RootJsonSchema:
    schema: Union[str, UndefinedType] = field(
        default=Undefined, metadata=alias("$schema")
    )
    defs: list[JsonSchema] = field(default_factory=list, metadata=alias("$defs"))
    # This field schema is merged inside the owning one
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
assert serialize(RootJsonSchema, root_schema) == data
assert deserialization_schema(RootJsonSchema) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
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
    "type": "object",
    # It results in allOf + unevaluatedProperties=False
    "allOf": [
        # RootJsonSchema (without JsonSchema)
        {
            "type": "object",
            "properties": {
                "$schema": {"type": "string"},
                "$defs": {"type": "array", "items": {"$ref": "#/$defs/JsonSchema"}},
            },
            "additionalProperties": False,
        },
        # JonsSchema
        {"$ref": "#/$defs/JsonSchema"},
    ],
    "unevaluatedProperties": False,
}
