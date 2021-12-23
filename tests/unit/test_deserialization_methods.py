from apischema.deserialization.methods import to_hashable


def test_to_hashable():
    hashable1 = to_hashable({"key1": 0, "key2": [1, 2]})
    hashable2 = to_hashable({"key2": [1, 2], "key1": 0})
    assert hashable1 == hashable2
    assert hash(hashable1) == hash(hashable2)
