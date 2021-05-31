from apischema import deserialize, schema


def test_int_as_float():
    assert deserialize(float, 42) == 42.0
    assert deserialize(float, 42, schema=schema(min=0)) == 42.0
