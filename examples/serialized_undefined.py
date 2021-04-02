from dataclasses import dataclass
from typing import Union

from apischema import Undefined, UndefinedType, serialize, serialized
from apischema.json_schema import serialization_schema


@dataclass
class Foo:
    @serialized
    def bar(self) -> Union[int, UndefinedType]:
        return Undefined


assert serialize(Foo()) == {}
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "additionalProperties": False,
}
