from typing import Any, NewType, Tuple

from dataclasses import dataclass

from apischema import (
    converter,
    from_data,
    input_converter,
    output_converter,
    schema,
    to_data,
)

HexaRGB = NewType("HexaRGB", str)
schema(pattern="^#[0-9a-fA-F]{6}$")(HexaRGB)

U8 = NewType("U8", int)
schema(min=0, max=256)(U8)

RGBTuple: Any = Tuple[U8, U8, U8]


@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @output_converter
    def hexa(self) -> HexaRGB:
        return HexaRGB(f"#{self.red:02x}{self.green:02x}{self.blue:02x}")

    @converter
    def tuple(self) -> RGBTuple:
        return U8(self.red), U8(self.green), U8(self.blue)


@input_converter
def rgb_from_str(hexa: HexaRGB) -> RGB:
    return RGB(int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16))


@input_converter
def rgb_from_tuple(rgb: RGBTuple) -> RGB:
    return RGB(*rgb)


def test_rgb():
    assert from_data(RGB, "#000000") == from_data(RGB, [0, 0, 0]) == RGB(0, 0, 0)
    assert to_data(RGB(0, 0, 42)) == "#00002a"  # output_converter is default converter
    assert to_data(RGB(0, 0, 42), conversions={RGB: RGBTuple}) == [0, 0, 42]


# Standard library types like UUID or datetime are handled this way
# see std_types.py
