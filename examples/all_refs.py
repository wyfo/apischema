from dataclasses import dataclass

from apischema.json_schema import deserialization_schema


@dataclass
class Bar:
    baz: str


@dataclass
class Foo:
    bar1: Bar
    bar2: Bar


assert deserialization_schema(Foo, all_refs=False) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$defs": {
        "Bar": {
            "additionalProperties": False,
            "properties": {"baz": {"type": "string"}},
            "required": ["baz"],
            "type": "object",
        }
    },
    "additionalProperties": False,
    "properties": {"bar1": {"$ref": "#/$defs/Bar"}, "bar2": {"$ref": "#/$defs/Bar"}},
    "required": ["bar1", "bar2"],
    "type": "object",
}
assert deserialization_schema(Foo, all_refs=True) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$defs": {
        "Bar": {
            "additionalProperties": False,
            "properties": {"baz": {"type": "string"}},
            "required": ["baz"],
            "type": "object",
        },
        "Foo": {
            "additionalProperties": False,
            "properties": {
                "bar1": {"$ref": "#/$defs/Bar"},
                "bar2": {"$ref": "#/$defs/Bar"},
            },
            "required": ["bar1", "bar2"],
            "type": "object",
        },
    },
    "$ref": "#/$defs/Foo",
}
