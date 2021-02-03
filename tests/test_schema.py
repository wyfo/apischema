from dataclasses import dataclass
from typing import Optional

from apischema import deserializer
from apischema.json_schema import deserialization_schema


class Foo:
    pass


@dataclass
class Bar:
    foo: Optional[Foo]


@deserializer
def foo(bar: Bar) -> Foo:
    return bar.foo or Foo()


def test_recursive_by_conversion_schema():
    assert deserialization_schema(Foo) == {
        "$ref": "#/$defs/Bar",
        "$defs": {
            "Bar": {
                "type": "object",
                "properties": {
                    "foo": {"anyOf": [{"$ref": "#/$defs/Bar"}, {"type": "null"}]}
                },
                "required": ["foo"],
                "additionalProperties": False,
            }
        },
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
    }
