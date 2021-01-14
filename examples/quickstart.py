from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4

from graphql import print_schema
from pytest import raises

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
