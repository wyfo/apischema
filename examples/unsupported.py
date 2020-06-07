from pytest import raises

from apischema import Unsupported, deserialize, serialize


class Foo:
    pass


with raises(Unsupported):
    deserialize(Foo, {})
with raises(Unsupported):
    serialize(Foo())
