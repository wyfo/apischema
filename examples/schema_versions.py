from dataclasses import dataclass
from typing import Optional

from apischema.json_schema import (
    JsonSchemaVersion,
    definitions_schema,
    deserialization_schema,
)


@dataclass
class Bar:
    baz: Optional[int]


@dataclass
class Foo:
    bar: Bar


assert deserialization_schema(Foo, all_refs=True) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$ref": "#/$defs/Foo",
    "$defs": {
        "Foo": {
            "type": "object",
            "properties": {"bar": {"$ref": "#/$defs/Bar"}},
            "required": ["bar"],
            "additionalProperties": False,
        },
        "Bar": {
            "type": "object",
            "properties": {"baz": {"type": ["integer", "null"]}},
            "required": ["baz"],
            "additionalProperties": False,
        },
    },
}
assert deserialization_schema(
    Foo, all_refs=True, version=JsonSchemaVersion.DRAFT_7
) == {
    "$schema": "http://json-schema.org/draft-07/schema#",
    # $ref is isolated in allOf + draft 7 prefix
    "allOf": [{"$ref": "#/definitions/Foo"}],
    "definitions": {  # not "$defs"
        "Foo": {
            "type": "object",
            "properties": {"bar": {"$ref": "#/definitions/Bar"}},
            "required": ["bar"],
            "additionalProperties": False,
        },
        "Bar": {
            "type": "object",
            "properties": {"baz": {"type": ["integer", "null"]}},
            "required": ["baz"],
            "additionalProperties": False,
        },
    },
}
assert deserialization_schema(Foo, version=JsonSchemaVersion.OPEN_API_3_0) == {
    # No definitions for OpenAPI, use definitions_schema for it
    "$ref": "#/components/schemas/Foo",  # OpenAPI prefix
}
assert definitions_schema(
    deserialization=[Foo], version=JsonSchemaVersion.OPEN_API_3_0
) == {
    "Foo": {
        "type": "object",
        "properties": {"bar": {"$ref": "#/components/schemas/Bar"}},
        "required": ["bar"],
        "additionalProperties": False,
    },
    "Bar": {
        "type": "object",
        # "nullable" instead of "type": "null"
        "properties": {"baz": {"type": "integer", "nullable": True}},
        "required": ["baz"],
        "additionalProperties": False,
    },
}
