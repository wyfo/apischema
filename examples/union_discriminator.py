from dataclasses import dataclass
from typing import Annotated, Union

import pytest

from apischema import (
    ValidationError,
    deserialization_method,
    deserialize,
    discriminator,
    serialize,
)
from apischema.json_schema import deserialization_schema


@dataclass
class Cat:
    pass


@dataclass
class Dog:
    pass


@dataclass
class Lizard:
    pass


Pet = Annotated[Union[Cat, Dog, Lizard], discriminator("type", {"dog": Dog})]

assert deserialize(Pet, {"type": "dog"}) == Dog()
assert deserialize(Pet, {"type": "Cat"}) == Cat()
assert serialize(Pet, Dog()) == {"type": "dog"}
with pytest.raises(ValidationError) as err:
    assert deserialize(Pet, {"type": "not a pet"})
assert err.value.errors == [
    {"loc": ["type"], "err": "not one of ['dog', 'Cat', 'Lizard'] (oneOf)"}
]

assert deserialization_schema(Pet) == {
    "oneOf": [
        {"$ref": "#/$defs/Cat"},
        {"$ref": "#/$defs/Dog"},
        {"$ref": "#/$defs/Lizard"},
    ],
    "discriminator": {"propertyName": "type", "mapping": {"dog": "#/$defs/Dog"}},
    "$defs": {
        "Dog": {"type": "object", "additionalProperties": False},
        "Cat": {"type": "object", "additionalProperties": False},
        "Lizard": {"type": "object", "additionalProperties": False},
    },
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
}
