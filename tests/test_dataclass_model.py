from dataclasses import dataclass, field
from typing import Type, cast

from pytest import mark

from apischema import alias, deserialize, serialize
from apischema.conversions.dataclass_models import dataclass_model
from apischema.json_schema import deserialization_schema, serialization_schema


class Data:
    def __init__(self, a: int):
        self.a = a

    def __eq__(self, other):
        return type(other) == Data and other.a == self.a


@dataclass
class DataModel1:
    a: int


@dataclass
class DataModel2:
    a: int = field(metadata=alias("b"))


d_conv1, s_conv1 = dataclass_model(Data, DataModel1)
d_conv2, s_conv2 = dataclass_model(Data, DataModel2)
tmp: Type = cast(Type, ...)
d_conv3, s_conv3 = dataclass_model(Data, lambda: tmp)
# Assign tmp after dataclass_model call to show that it's called lazily
tmp = DataModel1


@mark.parametrize(
    "d_conv, s_conv, alias",
    [(d_conv1, s_conv1, "a"), (d_conv2, s_conv2, "b"), (d_conv3, s_conv3, "a")],
)
def test_simple_dataclass_model(d_conv, s_conv, alias):
    assert deserialize(Data, {alias: 0}, conversions=d_conv) == Data(0)
    assert serialize(Data, Data(0), conversions=s_conv) == {alias: 0}
    assert (
        deserialization_schema(Data, conversions=d_conv)
        == serialization_schema(Data, conversions=s_conv)
        == {
            "$schema": "http://json-schema.org/draft/2019-09/schema#",
            "type": "object",
            "properties": {alias: {"type": "integer"}},
            "required": [alias],
            "additionalProperties": False,
        }
    )
