from apischema import deserialize, deserializer, type_name
from apischema.json_schema import deserialization_schema
from apischema.objects import object_deserialization


def create_range(start: int, stop: int, step: int = 1) -> range:
    return range(start, stop, step)


range_conv = object_deserialization(create_range, type_name("Range"))
# Conversion can be registered
deserializer(range_conv)
assert deserialize(range, {"start": 0, "stop": 10}) == range(0, 10)
assert deserialization_schema(range) == {
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
