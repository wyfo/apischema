from apischema.utils import to_camel_case, to_hashable


def test_to_hashable():
    hashable1 = to_hashable({"key1": 0, "key2": [1, 2]})
    hashable2 = to_hashable({"key2": [1, 2], "key1": 0})
    assert hashable1 == hashable2
    assert hash(hashable1) == hash(hashable2)


def test_to_camel_case():
    assert to_camel_case("min_length") == "minLength"
