from dataclasses import dataclass, field

from apischema.json_schema import deserialization_schema
from apischema.metadata import skip


@dataclass
class Foo:
    bar: int
    baz: str = field(default="baz", metadata=skip)


assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "required": ["bar"],
    "additionalProperties": False,
}
