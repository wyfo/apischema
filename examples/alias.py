from dataclasses import dataclass, field

from apischema import alias, deserialize, serialize
from apischema.json_schema import deserialization_schema


@dataclass
class Foo:
    class_: str = field(metadata=alias("class"))


assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "additionalProperties": False,
    "properties": {"class": {"type": "string"}},
    "required": ["class"],
    "type": "object",
}
assert deserialize(Foo, {"class": "bar"}) == Foo("bar")
assert serialize(Foo, Foo("bar")) == {"class": "bar"}
