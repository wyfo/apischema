from dataclasses import dataclass
from typing import Literal, Union

from apischema import deserialize, discriminator
from apischema.json_schema import deserialization_schema


@discriminator("type")
class Pet:
    pass


@dataclass
class Cat(Pet):
    type: Literal["cat"]


@dataclass
class Dog(Pet):
    type: Literal["dog"]


assert deserialize(Union[Cat, Dog], {"type": "dog"}) == Dog("dog")


assert deserialization_schema(Union[Cat, Dog]) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "anyOf": [{"$ref": "#/$defs/Cat"}, {"$ref": "#/$defs/Dog"}],
    "$defs": {
        "Cat": {
            "allOf": [
                {"$ref": "#/$defs/Pet"},
                {
                    "type": "object",
                    "properties": {"type": {"type": "string", "const": "cat"}},
                    "required": ["type"],
                    "additionalProperties": False,
                },
            ]
        },
        "Pet": {
            "type": "object",
            "required": ["type"],
            "properties": {"type": {"type": "string"}},
            "discriminator": {"property_name": "type"},
        },
        "Dog": {
            "allOf": [
                {"$ref": "#/$defs/Pet"},
                {
                    "type": "object",
                    "properties": {"type": {"type": "string", "const": "dog"}},
                    "required": ["type"],
                    "additionalProperties": False,
                },
            ]
        },
    },
}
