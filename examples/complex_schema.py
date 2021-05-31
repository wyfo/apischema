from dataclasses import dataclass
from typing import Optional

from apischema.json_schema import deserialization_schema


@dataclass
class Node:
    value: int
    child: Optional["Node"] = None


assert deserialization_schema(Node) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$ref": "#/$defs/Node",
    "$defs": {
        "Node": {
            "type": "object",
            "properties": {
                "value": {"type": "integer"},
                "child": {
                    "anyOf": [{"$ref": "#/$defs/Node"}, {"type": "null"}],
                    "default": None,
                },
            },
            "required": ["value"],
            "additionalProperties": False,
        }
    },
}
