from dataclasses import dataclass
from typing import Annotated, Any, Union

from apischema import schema
from apischema.json_schema import deserialization_schema


# schema extra can be callable to modify the schema in place
def to_one_of(schema: dict[str, Any]):
    if "anyOf" in schema:
        schema["oneOf"] = schema.pop("anyOf")


OneOf = schema(extra=to_one_of)


# or extra can be a dictionary which will update the schema
@schema(
    extra={"$ref": "http://some-domain.org/path/to/schema.json#/$defs/Foo"},
    override=True,  # override apischema generated schema, using only extra
)
@dataclass
class Foo:
    bar: int


# Use Annotated with OneOf to make a "strict" Union
assert deserialization_schema(Annotated[Union[Foo, int], OneOf]) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "oneOf": [  # oneOf instead of anyOf
        {"$ref": "http://some-domain.org/path/to/schema.json#/$defs/Foo"},
        {"type": "integer"},
    ],
}
