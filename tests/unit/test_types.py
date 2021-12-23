from apischema.types import MetadataImplem, MetadataMixin


def test_metadata():
    metadata = MetadataImplem({"a": 0, "b": 1})
    assert metadata | {"b": 2} == {"a": 0, "b": 2}
    assert {"b": 2} | metadata == metadata


class KeyMetadata(MetadataMixin):
    key = "key"


def test_metadata_mixin():
    instance = KeyMetadata()
    assert list(instance.items()) == [("key", instance)]
