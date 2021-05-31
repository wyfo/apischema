from dataclasses import dataclass

from apischema.json_schema import definitions_schema


@dataclass
class Bar:
    baz: int = 0


@dataclass
class Foo:
    bar: Bar


assert definitions_schema(deserialization=[list[Foo]], all_refs=True) == {
    "Foo": {
        "type": "object",
        "properties": {"bar": {"$ref": "#/$defs/Bar"}},
        "required": ["bar"],
        "additionalProperties": False,
    },
    "Bar": {
        "type": "object",
        "properties": {"baz": {"type": "integer", "default": 0}},
        "additionalProperties": False,
    },
}
