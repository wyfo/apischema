from dataclasses import dataclass, field
from typing import Any, Mapping

from apischema import (build_input_schema, properties,
                       schema, to_data)
from apischema.typing import Annotated


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
    cls = Mapping[Annotated[str, schema(pattern=r"\w{2}")], int]
    assert to_data(build_input_schema(cls)) == {
        "type":              "object",
        "patternProperties": {
            r"\w{2}": {"type": "integer"}
        }
    }
