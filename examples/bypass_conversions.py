from dataclasses import dataclass

from apischema import serialize, serializer
from apischema.conversions import identity


@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @serializer
    @property
    def hexa(self) -> str:
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"


assert serialize(RGB(0, 0, 0)) == "#000000"
# dynamic conversion used to bypass the registered one
assert serialize(RGB(0, 0, 0), conversions=identity) == {
    "red": 0,
    "green": 0,
    "blue": 0,
}
