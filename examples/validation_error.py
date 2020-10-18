from dataclasses import dataclass, field
from typing import NewType

from pytest import raises

from apischema import ValidationError, deserialize, schema, serialize

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
assert serialize(err.value) == [
    {
        "loc": ["tags"],
        "err": ["size greater than 3 (maxItems)", "duplicate items (uniqueItems)"],
    },
    {"loc": ["tags", 3], "err": ["'^\\w*$' not matched (pattern)"]},
    {"loc": ["tags", 4], "err": ["length less than 3 (minLength)"]},
]
