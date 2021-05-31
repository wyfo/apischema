from dataclasses import dataclass
from typing import Annotated

from apischema import alias, deserialize
from apischema.conversions import dataclass_input_wrapper
from apischema.json_schema import deserialization_schema


@dataclass
class Foo:
    bar: str


# Annotated can be used to add metadata to mapped fields
def prefixed_foo(baz: str, pfx: Annotated[str, alias("prefix")] = "") -> Foo:
    return Foo(pfx + baz)


wrapper, input_cls = dataclass_input_wrapper(prefixed_foo)

assert wrapper(input_cls("oo", "f")) == prefixed_foo("oo", "f") == Foo("foo")

# Used as conversion
assert deserialize(Foo, {"baz": "oo", "prefix": "f"}, conversions=wrapper) == Foo("foo")
assert deserialization_schema(Foo, conversions=wrapper) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {
        "baz": {"type": "string"},
        "prefix": {"type": "string", "default": ""},
    },
    "required": ["baz"],
    "additionalProperties": False,
}
