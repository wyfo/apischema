from dataclasses import dataclass
from typing import Any

from apischema import alias, serialize, type_name
from apischema.json_schema import JsonSchemaVersion, definitions_schema
from apischema.objects import get_field, object_serialization


@dataclass
class Data:
    id: int
    content: str

    @property
    def size(self) -> int:
        return len(self.content)

    def get_details(self) -> Any: ...


# Serialization fields can be a str/field or a function/method/property
size_only = object_serialization(
    Data, [get_field(Data).id, Data.size], type_name("DataSize")
)
# ["id", Data.size] would also work


def complete_data():
    return [
        ...,  # shortcut to include all the fields
        Data.size,
        (Data.get_details, alias("details")),  # add/override metadata using tuple
    ]


# Serialization fields computation can be deferred in a function
# The serialization name will then be defaulted to the function name
complete = object_serialization(Data, complete_data)

data = Data(0, "data")
assert serialize(Data, data, conversion=size_only) == {"id": 0, "size": 4}
assert serialize(Data, data, conversion=complete) == {
    "id": 0,
    "content": "data",
    "size": 4,
    "details": None,  # because get_details return None in this example
}


assert definitions_schema(
    serialization=[(Data, size_only), (Data, complete)],
    version=JsonSchemaVersion.OPEN_API_3_0,
) == {
    "DataSize": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "size": {"type": "integer"}},
        "required": ["id", "size"],
        "additionalProperties": False,
    },
    "CompleteData": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "content": {"type": "string"},
            "size": {"type": "integer"},
            "details": {},
        },
        "required": ["id", "content", "size", "details"],
        "additionalProperties": False,
    },
}
