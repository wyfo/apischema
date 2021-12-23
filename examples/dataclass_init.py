from dataclasses import InitVar, dataclass, field

import pytest

from apischema import ValidationError, deserialize, serialize, validator
from apischema.json_schema import definitions_schema
from apischema.metadata import init_var


@dataclass
class Foo:
    bar: int
    init_only: InitVar[int] = field(metadata=init_var(int))
    no_init: int = field(init=False)

    def __post_init__(self, init_only: int):
        self.no_init = init_only

    # InitVar are passed as kwargs, like in __post_init__
    @validator
    def validate(self, init_only: int):
        if self.bar == init_only:
            raise ValueError("Error")


assert deserialize(Foo, {"bar": 0, "init_only": 1}) == Foo(0, 1)
assert serialize(Foo, Foo(0, 1)) == {"bar": 0, "no_init": 1}
with pytest.raises(ValidationError) as err:
    deserialize(Foo, {"bar": 0})
assert definitions_schema(
    deserialization=[Foo], serialization=[Foo], all_refs=True
) == {
    "Foo": {
        "type": "object",
        "properties": {
            "bar": {"type": "integer"},
            "no_init": {"readOnly": True, "type": "integer"},
            "init_only": {"writeOnly": True, "type": "integer"},
        },
        "additionalProperties": False,
        "required": ["bar", "init_only"],
    }
}
