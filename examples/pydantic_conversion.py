import re
from typing import NamedTuple, NewType

import pydantic.validators

import apischema


# Serialization can only be customized into the enclosing models
class RGB(NamedTuple):
    red: int
    green: int
    blue: int

    # If you don't put this method, RGB schema will be:
    # {'title': 'Rgb', 'type': 'array', 'items': {}}
    @classmethod
    def __modify_schema__(cls, field_schema) -> None:
        field_schema.update({"type": "string", "pattern": r"#[0-9A-Fa-f]{6}"})
        field_schema.pop("items", ...)

    @classmethod
    def __get_validators__(cls):
        yield pydantic.validators.str_validator
        yield cls.validate

    @classmethod
    def validate(cls, value) -> "RGB":
        if (
            not isinstance(value, str)
            or re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is None
        ):
            raise ValueError("Invalid RGB")
        return RGB(
            red=int(value[1:3], 16), green=int(value[3:5], 16), blue=int(value[5:7], 16)
        )


# Simpler with apischema


class RGB(NamedTuple):
    red: int
    green: int
    blue: int


# NewType can be used to add schema to conversion source/target
# but Annotated[str, apischema.schema(pattern=r"#[0-9A-Fa-f]{6}")] would have worked too
HexaRGB = NewType("HexaRGB", str)
# pattern is used in JSON schema and in deserialization validation
apischema.schema(pattern=r"#[0-9A-Fa-f]{6}")(HexaRGB)


@apischema.deserializer  # could be declared as a staticmethod of RGB class
def from_hexa(hexa: HexaRGB) -> RGB:
    return RGB(int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16))


@apischema.serializer  # could be declared as a method/property of RGB class
def to_hexa(rgb: RGB) -> HexaRGB:
    return HexaRGB(f"#{rgb.red:02x}{rgb.green:02x}{rgb.blue:02x}")


assert (  # schema is inherited from deserialized type
    apischema.json_schema.deserialization_schema(RGB)
    == apischema.json_schema.deserialization_schema(HexaRGB)
    == {
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
        "type": "string",
        "pattern": "#[0-9A-Fa-f]{6}",
    }
)
