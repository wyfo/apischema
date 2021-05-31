from apischema import serialize, serializer


class Foo:
    pass


@serializer
def serialize_foo(foo: Foo) -> int:
    return 0


class Foo2(Foo):
    pass


# Deserializer is inherited
assert serialize(Foo, Foo()) == serialize(Foo2, Foo2()) == 0


class Bar:
    @serializer
    def serialize(self) -> int:
        return 0


class Bar2(Bar):
    def serialize(self) -> int:
        return 1


# Deserializer is inherited and overridden
assert serialize(Bar, Bar()) == 0 != serialize(Bar2, Bar2()) == 1
