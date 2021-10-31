from dataclasses import dataclass, field
from typing import NewType

from pytest import raises

from apischema import ValidationError, deserialize, schema

Tag = NewType("Tag", str)
schema(min_len=3, pattern=r"^\w*$", examples=["available", "EMEA"])(Tag)


@dataclass
class Resource:
    id: int
    tags: list[Tag] = field(
        default_factory=list,
        metadata=schema(
            description="regroup multiple resources", max_items=3, unique=True
        ),
    )


with raises(ValidationError) as err:  # pytest check exception is raised
    deserialize(
        Resource, {"id": 42, "tags": ["tag", "duplicate", "duplicate", "bad&", "_"]}
    )
assert err.value.errors == [
    {"loc": ["tags"], "msg": "item count greater than 3 (maxItems)"},
    {"loc": ["tags"], "msg": "duplicate items (uniqueItems)"},
    {"loc": ["tags", 3], "msg": 'not matching pattern "^\\w*$" (pattern)'},
    {"loc": ["tags", 4], "msg": "string length lower than 3 (minLength)"},
]
