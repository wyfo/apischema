from dataclasses import dataclass

from apischema import deserialize, schema, serialize
from apischema.conversions import deserializer, serializer
from apischema.json_schema import deserialization_schema, serialization_schema


@schema(pattern=r"^#[0-9a-fA-F]{6}$")
@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @serializer
    @property
    def hexa(self) -> str:
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"


# serializer can also be called with methods/properties outside of the class
# For example, `serializer(RGB.hexa)` would have the same effect as the decorator above


@deserializer
def from_hexa(hexa: str) -> RGB:
    return RGB(int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16))


assert deserialize(RGB, "#000000") == RGB(0, 0, 0)
assert serialize(RGB, RGB(0, 0, 42)) == "#00002a"
assert (
    deserialization_schema(RGB)
    == serialization_schema(RGB)
    == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "string",
        "pattern": "^#[0-9a-fA-F]{6}$",
    }
)
