from dataclasses import dataclass

from apischema.conversions import dataclass_model
from apischema.json_schema import deserialization_schema


class Foo:
    def __init__(self, bar):
        self.bar = bar


@dataclass_model(Foo)
@dataclass
class FooModel:
    bar: int


assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "required": ["bar"],
    "additionalProperties": False,
}
