# Apischema

Makes your life easier when it comes to python API.

JSON (de)serialization + schema generation through python typing, with a spoonful of sugar.

## Documentation

[https://wyfo.github.io/apischema/](https://wyfo.github.io/apischema/)

## Install
```shell
pip install apischema
```
It requires only Python 3.6+ (and dataclasses [official backport](https://pypi.org/project/dataclasses/) for version 3.6 only)

## Why another library?

This library fulfill the following goals:

- stay as close as possible to the standard library (dataclasses, typing, etc.) to be as accessible as possible — as a consequence do not need plugins for editor/linter/etc.;
- be additive and tunable, be able to work with user own types as well as foreign libraries ones; do not need a PR for handling new types like `bson.ObjectId`;
- avoid dynamic things like using string for attribute name.

No known alternative achieves that.

(Actually, *Apischema* is even adaptable enough to enable support of "rival" libraries in a few dozens of line of code)

## Example

```python
from dataclasses import dataclass, field
from typing import Set
from uuid import UUID, uuid4

from pytest import raises

from apischema import ValidationError, deserialize, serialize
from apischema.json_schema import deserialization_schema


# Define a schema with standard dataclasses
@dataclass
class Resource:
    id: UUID
    name: str
    tags: Set[str] = field(default_factory=set)


# Get some data
uuid = uuid4()
data = {"id": str(uuid), "name": "wyfo", "tags": ["some_tag"]}
# Deserialize data
resource = deserialize(Resource, data)
assert resource == Resource(uuid, "wyfo", {"some_tag"})
# Serialize objects
assert serialize(resource) == data
# Validate during deserialization
with raises(ValidationError) as err:  # pytest check exception is raised
    deserialize(Resource, {"id": "42", "name": "wyfo"})
assert serialize(err.value) == [  # ValidationError is serializable
    {"loc": ["id"], "err": ["badly formed hexadecimal UUID string"]}
]
# Generate JSON Schema
assert deserialization_schema(Resource) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "name": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
    "required": ["id", "name"],
    "additionalProperties": False,
}
```
*Apischema* works out of the box with your data model.

[*Let's start the Apischema tour.*](https://wyfo.github.io/apischema/)

