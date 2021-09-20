from enum import Enum

from apischema import deserialize, serialize
from apischema.conversions import as_names
from apischema.json_schema import deserialization_schema, serialization_schema


@as_names
class MyEnum(Enum):
    FOO = object()
    BAR = object()


assert deserialize(MyEnum, "FOO") == MyEnum.FOO
assert serialize(MyEnum, MyEnum.FOO) == "FOO"
assert (
    deserialization_schema(MyEnum)
    == serialization_schema(MyEnum)
    == {
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
        "type": "string",
        "enum": ["FOO", "BAR"],
    }
)
