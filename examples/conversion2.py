from __future__ import annotations

from typing import Collection

from apischema import converter, output_converter, to_data
from apischema.typing import TypedDict


class LightSerialization(TypedDict):
    id: int
    owner: str


class FullSerialization(TypedDict):
    id: int
    owner: str
    tags: Collection[str]


class OrmEntity:
    def __init__(self, id: int, owner: str, tags: Collection[str]):
        self.id = id
        self.owner = owner
        self.tags = tags

    @converter
    def to_dict_light(self) -> LightSerialization:
        return {"id": self.id, "owner": self.owner}

    @output_converter
    def to_dict(self) -> FullSerialization:
        return {"id": self.id, "owner": self.owner, "tags": self.tags}


def test_conversion():
    entity1 = OrmEntity(1, "me", ["tag"])
    entity2 = OrmEntity(2, "me", [])
    assert to_data(entity1) == {
        "id":    1,
        "owner": "me",
        "tags":  ["tag"]
    } == to_data(entity1, conversions={OrmEntity: FullSerialization})
    entities = [entity1, entity2]
    assert to_data(entities, conversions={OrmEntity: LightSerialization}) == [
        {
            "id":    1,
            "owner": "me"
        },
        {
            "id":    2,
            "owner": "me"
        }
    ]
