from apischema import deserialize
from apischema.conversion import inherited_deserializer


class Foo:
    def __init__(self, n: int):
        self.n = int

    def __eq__(self, other):
        return type(self) == type(other) and self.n == other.n

    @inherited_deserializer
    @classmethod
    def from_int(cls, n: int):
        return cls(n)


class Bar(Foo):
    pass


assert deserialize(Foo, 0) == Foo(0)
assert deserialize(Bar, 0) == Bar(0) != Foo(0)
