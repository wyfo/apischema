from dataclasses import dataclass
from typing import Optional

from apischema import deserialize
from apischema.fields import (
    fields_set,
    is_set,
    set_fields,
    unset_fields,
    with_fields_set,
)


# This decorator enable the feature
@with_fields_set
@dataclass
class Foo:
    bar: int
    baz: Optional[str] = None


# Retrieve fields set
foo1 = Foo(0, None)
assert fields_set(foo1) == {"bar", "baz"}
foo2 = Foo(0)
assert fields_set(foo2) == {"bar"}
# Test fields individually (with autocompletion and refactoring)
assert is_set(foo1).baz
assert not is_set(foo2).baz
# Mark fields as set/unset
set_fields(foo2, "baz")
assert fields_set(foo2) == {"bar", "baz"}
unset_fields(foo2, "baz")
assert fields_set(foo2) == {"bar"}
set_fields(foo2, "baz", overwrite=True)
assert fields_set(foo2) == {"baz"}
# Fields modification are taken in account
foo2.bar = 0
assert fields_set(foo2) == {"bar", "baz"}
# Because deserialization use normal constructor, it works with the feature
foo3 = deserialize(Foo, {"bar": 0})
assert fields_set(foo3) == {"bar"}
