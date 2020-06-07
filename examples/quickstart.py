from dataclasses import dataclass, field
from typing import Set
from uuid import UUID, uuid4

from pytest import raises

from apischema import ValidationError, deserialize, serialize

# Define a schema with standard dataclasses
from apischema.json_schema import deserialization_schema


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
