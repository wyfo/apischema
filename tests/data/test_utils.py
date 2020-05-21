from pytest import raises

from apischema.data import items_to_data


def test_items_to_data():
    lines = {
        "key1.0": "v0",
        "key1.2": "v2",
        "key2": 42,
    }
    assert items_to_data(lines.items()) == {"key1": ["v0", None, "v2"], "key2": 42}
    with raises(ValueError):
        items_to_data({"": ...}.items())
    with raises(ValueError):
        items_to_data({**lines, "key1.key3": ...}.items())
    with raises(ValueError):
        items_to_data({**lines, "0": ...}.items())
