from dataclasses import dataclass, field
from typing import Any

from apischema import alias
from apischema.json_schema import deserialization_schema


@alias(lambda s: f"foo_{s}")
@dataclass
class Foo:
    field1: Any
    field2: Any = field(metadata=alias(override=False))
    field3: Any = field(metadata=alias("field03"))
    field4: Any = field(metadata=alias("field04", override=False))


assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "additionalProperties": False,
    "properties": {"foo_field1": {}, "field2": {}, "foo_field03": {}, "field04": {}},
    "required": ["foo_field1", "field2", "foo_field03", "field04"],
    "type": "object",
}
