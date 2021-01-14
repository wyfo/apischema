# Apischema

Makes your life easier when it comes to python API.

JSON (de)serialization + *GraphQL* and JSON schema generation through python typing, with a spoonful of sugar.

## Documentation

[https://wyfo.github.io/apischema/](https://wyfo.github.io/apischema/)

## Install
```shell
pip install apischema
```
It requires only Python 3.6+ (and dataclasses [official backport](https://pypi.org/project/dataclasses/) for version 3.6 only)

*PyPy3* is fully supported.

## Why another library?

(If you wonder what the difference is with *pydantic* library, see the [dedicated section of the documentation](https://wyfo.github.io/apischema/pydantic_difference/), you will find a lot of difference.)

This library fulfills the following goals:

- stay as close as possible to the standard library (dataclasses, typing, etc.) — as a consequence do not need plugins for editors/linters/etc.;
- be additive and tunable, be able to work with user own types as well as foreign libraries ones; do not need a PR for handling new types like `bson.ObjectId` or `collection.deque`;
- avoid dynamic things like using string for attribute name;
- support *GraphQL*;
- (*Bonus*) be the fastest.

No known alternative achieves all of this.

## Example

```python
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4

from graphql import print_schema
from pytest import raises

from apischema import ValidationError, deserialize, serialize, graphql_schema
from apischema.json_schema import deserialization_schema


# Define a schema with standard dataclasses
@dataclass
class Resource:
    id: UUID
    name: str
    tags: set[str] = field(default_factory=set)


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

# Define GraphQL operations
def resources(tags: Optional[Collection[str]] = None) -> Optional[Collection[Resource]]:
    ...


# Generate GraphQL schema
schema = graphql_schema(query=[resources], id_types={UUID})
schema_str = """\
type Query {
  resources(tags: [String!]): [Resource!]
}

type Resource {
  id: ID!
  name: String!
  tags: [String!]!
}
"""
assert print_schema(schema) == schema_str
```
*Apischema* works out of the box with your data model.

[*Let's start the Apischema tour.*](https://wyfo.github.io/apischema/)

## Changelog

See [releases](https://github.com/wyfo/apischema/releases)