from dataclasses import dataclass, field
from typing import Literal, Union

from apischema import deserialize, discriminator
from apischema.json_schema import deserialization_schema


@dataclass
class Cat:
    type: str = field(metadata=discriminator)


@dataclass
class Dog:
    type: Literal["dog"] = field(metadata=discriminator)


assert deserialize(Union[Cat, Dog], {"type": "dog"}) == Dog("dog")
assert deserialization_schema(Union[Cat, Dog]) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "anyOf": [{"$ref": "#/$defs/Cat"}, {"$ref": "#/$defs/Dog"}],
    "discriminator": {"property_name": "type", "mapping": {"dog": "#/$defs/Dog"}},
    "$defs": {
        "Cat": {
            "type": "object",
            "properties": {"type": {"type": "string"}},
            "required": ["type"],
            "additionalProperties": False,
        },
        "Dog": {
            "type": "object",
            "properties": {"type": {"type": "string", "const": "dog"}},
            "required": ["type"],
            "additionalProperties": False,
        },
    },
}
