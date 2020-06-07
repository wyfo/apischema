from dataclasses import dataclass
from typing import NewType

from apischema import deserialize, deserializer, schema, serialize, serializer
from apischema.json_schema import deserialization_schema, serialization_schema

HexaRGB = NewType("HexaRGB", str)
schema(pattern=r"^#[0-9a-fA-F]{6}$")(HexaRGB)


@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @serializer
    def hexa(self) -> HexaRGB:
        return HexaRGB(f"#{self.red:02x}{self.green:02x}{self.blue:02x}")


@deserializer
def from_hexa(hexa: HexaRGB) -> "RGB":
    return RGB(int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16))


assert deserialize(RGB, "#000000") == RGB(0, 0, 0)
assert serialize(RGB(0, 0, 42)) == "#00002a"
assert (
    deserialization_schema(RGB)
    == serialization_schema(RGB)
    == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "string",
        "pattern": "^#[0-9a-fA-F]{6}$",
    }
)
