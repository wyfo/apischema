from pytest import raises

from apischema.deserialization import unflat_key_value


def test_items_to_data():
    lines = {
        "key1.0": "v0",
        "key1.2": "v2",
        "key2": 42,
    }
    assert unflat_key_value(lines.items()) == {
        "key1": ["v0", None, "v2"],
        "key2": 42,
    }
    with raises(ValueError):
        unflat_key_value({"": ...}.items())
    with raises(ValueError):
        unflat_key_value({**lines, "key1.key3": ...}.items())
    with raises(ValueError):
        unflat_key_value({**lines, "0": ...}.items())
