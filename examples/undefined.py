from dataclasses import dataclass

from apischema import Undefined, UndefinedType, deserialize, serialize
from apischema.json_schema import deserialization_schema


@dataclass
class Foo:
    bar: int | UndefinedType = Undefined
    baz: int | UndefinedType | None = Undefined


assert deserialize(Foo, {"bar": 0, "baz": None}) == Foo(0, None)
assert deserialize(Foo, {}) == Foo(Undefined, Undefined)
assert serialize(Foo, Foo(Undefined, 42)) == {"baz": 42}
# Foo.bar and Foo.baz are not required
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}, "baz": {"type": ["integer", "null"]}},
    "additionalProperties": False,
}
