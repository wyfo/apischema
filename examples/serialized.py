from dataclasses import dataclass

from apischema import serialize, serialized
from apischema.json_schema import serialization_schema


@dataclass
class Foo:
    @serialized
    @property
    def bar(self) -> int:
        return 0

    @serialized
    def baz(self, some_arg_with_default: str = "") -> str:
        return some_arg_with_default

    @serialized("aliased")
    @property
    def aliased_property(self) -> bool:
        return True


assert serialize(Foo()) == {"bar": 0, "baz": "", "aliased": True}
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {
        "bar": {"readOnly": True, "type": "integer"},
        "baz": {"readOnly": True, "type": "string"},
        "aliased": {"readOnly": True, "type": "boolean"},
    },
    "additionalProperties": False,
}
