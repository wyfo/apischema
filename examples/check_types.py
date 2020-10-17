from collections.abc import Set
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pytest import raises

from apischema import ValidationError, check_types, schema, serialize


@dataclass
class Resource:
    id: UUID
    tags: Set[str] = field(metadata=schema(max_items=3))


check_types(Resource, Resource(uuid4(), {"tag"}))  # no error
with raises(ValidationError) as err:
    check_types(Resource, Resource("id", {0}))  # type: ignore
assert serialize(err.value) == [
    {"loc": ["id"], "err": ["expected UUID, found type str"]},
    {"loc": ["tags", 0], "err": ["expected str, found type int"]},
]
too_many_tags = Resource(uuid4(), {"0", "1", "2", "3"})
assert check_types(Resource, too_many_tags, validate=False)  # just type checking
with raises(ValidationError) as err:
    check_types(Resource, too_many_tags)
assert serialize(err.value) == [
    {"loc": ["tags"], "err": ["size greater than 3 (maxItems)"]}
]
