import sys
from typing import Any, Mapping, NewType

from dataclasses import dataclass, field
from typing_extensions import Annotated

from apischema import (build_input_schema, properties,
                       schema, to_data)


@dataclass
class Data:
    startswith_a: Mapping[str, Any] = field(default_factory=dict,
                                            metadata=properties(r"a.*"))
    others: Mapping[str, Any] = field(default_factory=dict, metadata=properties())


def test_properties():
    assert to_data(build_input_schema(Data)) == {
        "type":              "object",
        "patternProperties": {
            r"a.*": {}
        },
        # "additional_properties": {} # implicit
    }


def test_mapping_pattern_properties():
    if sys.version_info >= (3, 7):
        cls = Mapping[Annotated[str, schema(pattern=r"\w{2}")], int]
    else:
        TwoLetters = schema(pattern=r"\w{2}")(NewType("TwoLetters", str))
        cls = Mapping[TwoLetters, int]
    assert to_data(build_input_schema(cls)) == {
        "type":              "object",
        "patternProperties": {
            r"\w{2}": {"type": "integer"}
        }
    }
