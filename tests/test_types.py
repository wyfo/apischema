from apischema.types import MappingWithUnion, MetadataMixin


def test_metadata():
    metadata = MappingWithUnion({"a": 0, "b": 1})
    assert metadata | {"b": 2} == {"a": 0, "b": 2}
    assert {"b": 2} | metadata == metadata


def test_metadata_mixin():
    instance = MetadataMixin("key")
    assert list(instance.items()) == [("key", instance)]
