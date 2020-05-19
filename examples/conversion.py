from dataclasses import dataclass
from typing import NewType

from apischema import (from_data, input_converter, output_converter, schema,
                       to_data)

HexaRGB = NewType("HexaRGB", str)
schema(pattern="^#[0-9a-fA-F]{6}$")(HexaRGB)


@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @output_converter
    def hexa(self) -> HexaRGB:
        return HexaRGB(f"#{self.red:02x}{self.green:02x}{self.blue:02x}")


@input_converter
def rgb_from_str(hexa: HexaRGB) -> RGB:
    return RGB(int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16))


def test_rgb():
    assert from_data(RGB, "#FFFFFF") == RGB(255, 255, 255)
    assert to_data(RGB(0, 0, 0)) == "#000000"

# Standard library types like UUID or datetime are handled this way
# see std_types.py
