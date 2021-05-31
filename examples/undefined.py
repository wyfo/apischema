from dataclasses import dataclass
from typing import Union

from apischema import Undefined, UndefinedType, deserialize, serialize
from apischema.json_schema import deserialization_schema


@dataclass
class Foo:
    bar: Union[int, UndefinedType] = Undefined
    baz: Union[int, UndefinedType, None] = Undefined


assert deserialize(Foo, {"bar": 0, "baz": None}) == Foo(0, None)
assert deserialize(Foo, {}) == Foo(Undefined, Undefined)
assert serialize(Foo, Foo(Undefined, 42)) == {"baz": 42}
# Foo.bar and Foo.baz are not required
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}, "baz": {"type": ["integer", "null"]}},
    "additionalProperties": False,
}
