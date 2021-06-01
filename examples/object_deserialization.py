from collections.abc import Iterable
from typing import Annotated

from apischema import deserialize, type_name
from apischema.json_schema import deserialization_schema
from apischema.metadata import conversion
from apischema.objects import object_deserialization


def create_range(start: int, stop: int, step: int = 1) -> Iterable[int]:
    return range(start, stop, step)


range_conv = object_deserialization(create_range, type_name=type_name("Range"))
Range = Annotated[Iterable[int], conversion(deserialization=range_conv)]
assert deserialize(Range, {"start": 0, "stop": 10}) == range(0, 10)
assert deserialization_schema(Range) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {
        "start": {"type": "integer"},
        "stop": {"type": "integer"},
        "step": {"type": "integer", "default": 1},
    },
    "required": ["start", "stop"],
    "additionalProperties": False,
}
