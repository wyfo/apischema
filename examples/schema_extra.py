from typing import NewType

from apischema import schema
from apischema.json_schema import deserialization_schema

Foo = NewType("Foo", str)
schema(min_len=20, extra={"typeName": "Foo"})(Foo)

Bar = NewType("Bar", int)
schema(
    extra={"$ref": "http://some-domain.org/path/tp/schema.json#/$defs/Bar"},
    override=True,
)(Bar)

assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "string",
    "minLength": 20,
    "typeName": "Foo",
}
assert deserialization_schema(Bar) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$ref": "http://some-domain.org/path/tp/schema.json#/$defs/Bar",
}
# Without override=True, it would be {
#     "$schema": "http://json-schema.org/draft/2019-09/schema#",
#     "$ref": "http://some-domain.org/path/tp/schema.json#/$defs/Bar",
#     "type": "integer",
# }
