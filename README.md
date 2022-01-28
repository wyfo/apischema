# apischema

JSON (de)serialization, GraphQL and JSON schema generation using Python typing.

*apischema* makes your life easier when dealing with API data.

## Documentation

[https://wyfo.github.io/apischema/](https://wyfo.github.io/apischema/)

## Install
```shell
pip install apischema
```
It requires only Python 3.6+ (and dataclasses [official backport](https://pypi.org/project/dataclasses/) for version 3.6 only)

*PyPy3* is fully supported.

## Why another library?

(If you wonder how this differs from the *pydantic* library, see the [dedicated section of the documentation(https://wyfo.github.io/apischema/0.17/difference_with_pydantic) — there are many differences.)

This library fulfills the following goals:

- stay as close as possible to the standard library (dataclasses, typing, etc.) — as a consequence we do not need plugins for editors/linters/etc.;
- avoid object-oriented limitations — do not require a base class — thus handle easily every type (`Foo`, `list[Bar]`, `NewType(Id, int)`, etc.) the same way.
- be adaptable, provide tools to support any types (ORM, etc.);
- avoid dynamic things like using raw strings for attributes name - play nicely with your IDE.

No known alternative achieves all of this, and apischema is also [(a lot) faster](https://wyfo.github.io/apischema/0.17/optimizations_and_benchmark#benchmark) than all of them.

On top of that, because APIs are not only JSON, *apischema* is also a complete GraphQL library

> Actually, *apischema* is even adaptable enough to enable support of competitor libraries in a few dozens of line of code ([pydantic support example](https://wyfo.github.io/apischema/0.17/examples/pydantic_support) using [conversions feature](https://wyfo.github.io/apischema/0.17/conversions))

## Example

```python
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
def resources(tags: Collection[str] | None = None) -> Collection[Resource] | None:
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
}"""
assert print_schema(schema) == schema_str
```
*apischema* works out of the box with your data model.

> This example and further ones are using *pytest* API because they are in fact run as tests in the library CI

### Run the documentation examples

All documentation examples are written using the last Python minor version — currently 3.10 — in order to provide up-to-date documentation. Because Python 3.10 specificities (like [PEP 585](https://www.python.org/dev/peps/pep-0604/)) are used, this version is "mandatory" to execute the examples as-is.

In addition to *pytest*, some examples use third-party libraries like *SQLAlchemy* or *attrs*. All of this dependencies can be downloaded using the `examples` extra with
```shell
pip install apischema[examples]
```

Once dependencies are installed, you can simply copy-paste examples and execute them, using the proper Python version. 

