from typing import NewType

from apischema import schema
from apischema.json_schema import deserialization_schema

Foo = NewType("Foo", str)
schema(min_len=20, extra={"typeName": "Foo"})(Foo)
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "string",
    "minLength": 20,
    "typeName": "Foo",
}

Bar = NewType("Bar", str)
schema(min_len=20, extra=lambda s: s.update({"typeName": "Bar"}))(Bar)
assert deserialization_schema(Bar) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "string",
    "minLength": 20,
    "typeName": "Bar",
}

Baz = NewType("Baz", int)
schema(
    extra={"$ref": "http://some-domain.org/path/to/schema.json#/$defs/Baz"},
    override=True,
)(Baz)
assert deserialization_schema(Baz) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$ref": "http://some-domain.org/path/to/schema.json#/$defs/Baz",
}
# Without override=True, it would be {
#     "$schema": "http://json-schema.org/draft/2019-09/schema#",
#     "$ref": "http://some-domain.org/path/to/schema.json#/$defs/Baz",
#     "type": "integer",
# }
