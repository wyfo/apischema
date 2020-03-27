from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from apischema import from_stringified, properties
from apischema.typing import Literal


class Strength(Enum):
    WEAK = "weak"
    STRONG = "strong"


Size = Literal["small", "big"]


@dataclass
class Config:
    strength: Strength = Strength.WEAK
    size: Size = "small"
    level: int = 0
    extra: Mapping[str, bool] = field(default_factory=dict,
                                      metadata=properties())


def test_from_stringified():
    lines = {"level": "42", "opt1": "ok", "opt2": "no"}
    assert from_stringified(lines.items(), Config) == Config(
        strength=Strength.WEAK,
        size="small",
        level=42,
        extra={"opt1": True, "opt2": False}
    )
