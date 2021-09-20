from dataclasses import dataclass, field
from typing import Any

from apischema.json_schema import deserialization_schema, serialization_schema
from apischema.metadata import skip


@dataclass
class Foo:
    bar: Any
    deserialization_only: Any = field(metadata=skip(serialization=True))
    serialization_only: Any = field(default=None, metadata=skip(deserialization=True))
    baz: Any = field(default=None, metadata=skip)


assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "type": "object",
    "properties": {"bar": {}, "deserialization_only": {}},
    "required": ["bar", "deserialization_only"],
    "additionalProperties": False,
}
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "type": "object",
    "properties": {"bar": {}, "serialization_only": {}},
    "required": ["bar", "serialization_only"],
    "additionalProperties": False,
}
