from dataclasses import dataclass, field
from typing import Optional

from pytest import raises

from apischema import ValidationError, deserialize, serialize
from apischema.json_schema import deserialization_schema, serialization_schema
from apischema.metadata import none_as_undefined


@dataclass
class Foo:
    bar: Optional[str] = field(default=None, metadata=none_as_undefined)


assert (
    deserialization_schema(Foo)
    == serialization_schema(Foo)
    == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "object",
        "properties": {"bar": {"type": "string"}},
        "additionalProperties": False,
    }
)
with raises(ValidationError):
    deserialize(Foo, {"bar": None})
assert serialize(Foo, Foo(None)) == {}
