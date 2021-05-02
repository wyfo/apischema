from dataclasses import dataclass

from apischema import deserialize, deserializer, serialize, serializer


@dataclass
class A:
    a: int

    @deserializer
    @staticmethod
    def from_int(a: int) -> "A":
        return A(a)

    @serializer
    def to_int(self) -> int:
        return self.a


@dataclass
class B:
    b: int

    @serializer
    @property
    def as_int(self) -> int:
        return self.b


def test_descriptor_converters():
    assert deserialize(A, 0) == A(0)
    assert serialize(A(0)) == serialize(B(0)) == 0
