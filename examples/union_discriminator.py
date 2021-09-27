from dataclasses import dataclass
from timeit import timeit
from typing import Annotated, Literal, Union

from pytest import raises

from apischema import (
    ValidationError,
    deserialization_method,
    deserialize,
    discriminator,
)
from apischema.json_schema import deserialization_schema


@dataclass
class Cat:
    type: Literal["Cat", "Lion"]
    ...


@dataclass
class Dog:
    type: str
    ...


@dataclass
class Lizard:
    type: str
    ...


Pet = Union[Cat, Dog, Lizard]
DiscriminatedPet = Annotated[Pet, discriminator("type", {"dog": Dog})]

for obj in [Cat("Cat"), Cat("Lion"), Dog("dog"), Lizard("Lizard")]:
    assert deserialize(DiscriminatedPet, {"type": obj.type}) == obj
with raises(ValidationError) as err:
    assert deserialize(DiscriminatedPet, {"type": "not a pet"})
assert err.value.errors == [
    {
        "loc": ["type"],
        "msg": "not one of ['dog', 'Cat', 'Lion', 'Lizard'] (discriminator)",
    }
]

assert deserialization_schema(DiscriminatedPet) == {
    "anyOf": [
        {"$ref": "#/$defs/Cat"},
        {"$ref": "#/$defs/Dog"},
        {"$ref": "#/$defs/Lizard"},
    ],
    "discriminator": {
        "property_name": "type",
        "mapping": {"dog": "#/$defs/Dog", "Cat": "#/$defs/Cat", "Lion": "#/$defs/Cat"},
        # mapping "Lizard": "#/$defs/Lizard" is implicit
    },
    "$defs": {
        "Dog": {
            "type": "object",
            "properties": {"type": {"type": "string"}},
            "required": ["type"],
            "additionalProperties": False,
        },
        "Cat": {
            "type": "object",
            "properties": {"type": {"type": "string", "enum": ["Cat", "Lion"]}},
            "required": ["type"],
            "additionalProperties": False,
        },
        "Lizard": {
            "type": "object",
            "properties": {"type": {"type": "string"}},
            "required": ["type"],
            "additionalProperties": False,
        },
    },
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
}


# Discriminator has a huge impact on performance
deserialize_union = deserialization_method(Pet)
deserialize_discriminated = deserialization_method(DiscriminatedPet)
print(timeit('deserialize_union({"type": "Cat"})', globals=globals()))
# 1.584252798
print(timeit('deserialize_union({"type": "dog"})', globals=globals()))
# 7.224892266 ≈ x4
print(timeit('deserialize_discriminated({"type": "Cat"})', globals=globals()))
# 1.648445550
print(timeit('deserialize_discriminated({"type": "dog"})', globals=globals()))
# 1.665450874 -> same
