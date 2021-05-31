from dataclasses import dataclass
from typing import Union

from apischema import serialize
from apischema.conversions import Conversion, LazyConversion


@dataclass
class Foo:
    elements: list[Union[int, "Foo"]]


def foo_elements(foo: Foo) -> list[Union[int, Foo]]:
    return foo.elements


# Recursive conversion pattern
tmp = None
conversion = Conversion(foo_elements, sub_conversions=LazyConversion(lambda: tmp))
tmp = conversion

assert serialize(Foo, Foo([0, Foo([1])]), conversions=conversion) == [0, [1]]
# Without the recursive sub-conversion, it would have been:
assert serialize(Foo, Foo([0, Foo([1])]), conversions=foo_elements) == [
    0,
    {"elements": [1]},
]
