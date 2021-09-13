from dataclasses import dataclass

from apischema import serialize, serialized
from apischema.json_schema import serialization_schema


@dataclass
class Foo:
    @serialized
    @property
    def bar(self) -> int:
        return 0

    # Serialized method can have default argument
    @serialized
    def baz(self, some_arg_with_default: int = 1) -> int:
        return some_arg_with_default

    @serialized("aliased")
    @property
    def with_alias(self) -> int:
        return 2


# Serialized method can also be defined outside class,
# but first parameter must be annotated
@serialized
def function(foo: Foo) -> int:
    return 3


assert serialize(Foo, Foo()) == {"bar": 0, "baz": 1, "aliased": 2, "function": 3}
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {
        "aliased": {"type": "integer"},
        "bar": {"type": "integer"},
        "baz": {"type": "integer"},
        "function": {"type": "integer"},
    },
    "required": ["bar", "baz", "aliased", "function"],
    "additionalProperties": False,
}
