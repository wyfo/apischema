from dataclasses import dataclass, field
from typing import Any, Mapping

from apischema import (alias, from_data, get_fields_set, properties, to_data,
                       with_fields_set)


@with_fields_set
@dataclass
class Serialized:
    cls: str = field(metadata=alias("class"))
    to_be_completed: bool = False
    properties: Mapping[str, Any] = field(default_factory=dict,
                                          metadata=properties())


def to_camel_case(s: str) -> str:
    pascal_case = "".join(map(str.capitalize, s.split("_")))
    return pascal_case[0].lower() + pascal_case[1:]


def test_serialized():
    data = {
        "class":  "Foo",
        "field1": 0,
        "field2": ["elt1", "elt2"]
    }
    serialized = from_data(Serialized, data)
    assert serialized == Serialized("Foo", properties={
        "field1": 0,
        "field2": ["elt1", "elt2"]
    })
    assert get_fields_set(serialized) == {"cls", "properties"}  # no to_be_completed
    assert to_data(serialized) == data
    assert to_data(serialized, exclude_unset=False) == {
        "class":           "Foo",
        "to_be_completed": False,
        "field1":          0,
        "field2":          ["elt1", "elt2"]
    }
