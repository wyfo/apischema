from dataclasses import dataclass
from typing import Union

from apischema import deserialize, discriminator, serialize
from apischema.json_schema import deserialization_schema


@discriminator("type")
class Pet:
    pass


@dataclass
class Cat(Pet):
    pass


@dataclass
class Dog(Pet):
    pass


data = {"type": "Dog"}
assert deserialize(Pet, data) == deserialize(Union[Cat, Dog], data) == Dog()
assert serialize(Pet, Dog()), serialize(Union[Cat, Dog], Dog()) == data


assert deserialization_schema(Union[Cat, Dog]) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "anyOf": [{"$ref": "#/$defs/Cat"}, {"$ref": "#/$defs/Dog"}],
    "$defs": {
        "Pet": {
            "type": "object",
            "required": ["type"],
            "properties": {"type": {"type": "string"}},
            "discriminator": {"propertyName": "type"},
        },
        "Cat": {"allOf": [{"$ref": "#/$defs/Pet"}, {"type": "object"}]},
        "Dog": {"allOf": [{"$ref": "#/$defs/Pet"}, {"type": "object"}]},
    },
}
