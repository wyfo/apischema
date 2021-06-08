from pytest import raises

from apischema import ValidationError, deserialize, schema


def test_int_as_float():
    assert deserialize(float, 42) == 42.0
    assert type(deserialize(float, 42)) == float
    assert deserialize(float, 42, schema=schema(min=0)) == 42.0
    with raises(ValidationError):
        deserialize(float, -1.0, schema=schema(min=0))
