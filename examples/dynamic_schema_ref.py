from dataclasses import dataclass

from apischema import schema_ref
from apischema.json_schema import serialization_schema


@dataclass
class Foo:
    pass


@dataclass
class Bar:
    pass


def foo_to_bar(_: Foo) -> Bar:
    return Bar()


schema_ref("Bars")(list[Bar])

assert serialization_schema(list[Foo], all_refs=True, conversions=foo_to_bar) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$ref": "#/$defs/Bars",
    "$defs": {
        # Bars is present because `list[Foo]` is dynamically converted to `list[Bar]`
        "Bars": {"type": "array", "items": {"$ref": "#/$defs/Bar"}},
        "Bar": {"type": "object", "additionalProperties": False},
    },
}
