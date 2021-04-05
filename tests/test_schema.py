from dataclasses import dataclass, field
from typing import NewType, Optional

from apischema import deserializer, schema, schema_ref
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


MoreThanTwo = NewType("MoreThanTwo", int)
schema(min=0, extra=lambda s: s.update({"minimum": 2}))(schema_ref(None)(MoreThanTwo))


@dataclass
class WithSchema:
    attr1: MoreThanTwo = field(metadata=schema(min=3))
    attr2: MoreThanTwo = field(metadata=schema(min=1))


def test_merged_schema():
    assert deserialization_schema(WithSchema) == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "object",
        "properties": {
            "attr1": {"type": "integer", "minimum": 3},
            "attr2": {"type": "integer", "minimum": 2},
        },
        "required": ["attr1", "attr2"],
        "additionalProperties": False,
    }
