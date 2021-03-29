from collections.abc import Iterator
from dataclasses import dataclass
from typing import TypeVar

from apischema import deserialize, deserializer
from apischema.conversions import Conversion

Foo_ = TypeVar("Foo_", bound="Foo")

# Use a dataclass in order to be easily testable with ==
@dataclass
class Foo:
    value: int

    @classmethod
    def deserialize(cls: type[Foo_], value: int) -> Foo_:
        return cls(value)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Register subclasses' conversion in __init_subclass__
        deserializer(Conversion(cls.deserialize, target=cls))


# Register main conversion after the class definition
deserializer(Conversion(Foo.deserialize, target=Foo))


class Bar(Foo):
    pass


assert deserialize(Foo, 0) == Foo(0)
assert deserialize(Bar, 0) == Bar(0)


# For external types (defines in imported library)


@dataclass
class ForeignType:
    value: int


class ForeignSubtype(ForeignType):
    pass


T = TypeVar("T")
# Recursive implementation of type.__subclasses__
def rec_subclasses(cls: type[T]) -> Iterator[type[T]]:
    for sub_cls in cls.__subclasses__():
        yield sub_cls
        yield from rec_subclasses(sub_cls)


# Register deserializers for all subclasses
for cls in (ForeignType, *rec_subclasses(ForeignType)):
    # cls=cls is an lambda idiom to capture variable by value inside loop
    deserializer(Conversion(lambda value, cls=cls: cls(value), source=int, target=cls))

assert deserialize(ForeignType, 0) == ForeignType(0)
assert deserialize(ForeignSubtype, 0) == ForeignSubtype(0)
