from collections.abc import Collection
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from graphql import print_schema

from apischema import ValidationError, deserialize, serialize
from apischema.graphql import graphql_schema
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
assert serialize(Resource, resource) == data
# Validate during deserialization
with pytest.raises(ValidationError) as err:  # pytest checks exception is raised
    deserialize(Resource, {"id": "42", "name": "wyfo"})
assert err.value.errors == [
    {"loc": ["id"], "err": "badly formed hexadecimal UUID string"}
]
# Generate JSON Schema
assert deserialization_schema(Resource) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "type": "object",
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "name": {"type": "string"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
            "default": [],
        },
    },
    "required": ["id", "name"],
    "additionalProperties": False,
}


# Define GraphQL operations
def resources(tags: Collection[str] | None = None) -> Collection[Resource] | None: ...


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
}"""
assert print_schema(schema) == schema_str
