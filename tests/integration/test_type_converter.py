from apischema import deserialize, deserializer


@deserializer
class Foo:
    def __init__(self, bar: int) -> None:
        self.bar = bar


def test_type_converter():
    foo = deserialize(Foo, 42)
    assert isinstance(foo, Foo) and foo.bar == 42
