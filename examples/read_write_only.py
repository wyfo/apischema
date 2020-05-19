from dataclasses import InitVar, dataclass, field

from apischema import (build_input_schema, build_output_schema, from_data,
                       schema, to_data)


@dataclass
class Data:
    init_field: InitVar[int]
    write_only_field: int = field(metadata=schema(write_only=True))
    not_init_field: int = field(init=False)
    read_only_field: int = field(default=42, metadata=schema(read_only=True))

    def __post_init__(self, init_field: int):
        self.not_init_field = init_field


def test_data():
    assert to_data(build_input_schema(Data)) == {
        "type":                 "object",
        "required":             ["init_field", "write_only_field"],
        "additionalProperties": False,
        "properties":           {
            "init_field":       {
                "type":      "integer",
                "writeOnly": True,
            },
            "write_only_field": {
                "type":      "integer",
                "writeOnly": True,
            },
            "read_only_field":  {
                "type":     "integer",
                "readOnly": True,
            }
        },
    }
    assert to_data(build_output_schema(Data)) == {
        "type":                 "object",
        "required":             ["write_only_field", "not_init_field"],
        "additionalProperties": False,
        "properties":           {
            "write_only_field": {
                "type":      "integer",
                "writeOnly": True,
            },
            "not_init_field":   {
                "type":     "integer",
                "readOnly": True,
            },
            "read_only_field":  {
                "type":     "integer",
                "readOnly": True,
            }
        },
    }
    data = from_data(Data, {"init_field": 0, "write_only_field": 1})
    assert data.write_only_field == 1
    assert data.not_init_field == 0
    assert data.read_only_field == 42
    # Support of readOnly/writeOnly is provisional because apischema works
    # with dual schema build_input_field/build_output_field (because of
    # conversions).
    # I could filter writeOnly properties at serialization (and readOnly at
    # deserialization), but this would make the code way more complex and I'm
    # not sure of the real interest of this "feature"
    assert to_data(data) != {
        "not_init_field":  0,
        "read_only_field": 42
    }
    assert to_data(data) == {
        "write_only_field": 1,
        "not_init_field":   0,
        "read_only_field":  42
    }
