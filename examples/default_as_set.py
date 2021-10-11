from dataclasses import dataclass, field

from apischema import serialize
from apischema.fields import with_fields_set
from apischema.metadata import default_as_set


# Decorator needed to benefit from the feature
@with_fields_set
@dataclass
class Foo:
    bar: int | None = field(default=None, metadata=default_as_set)


assert serialize(Foo, Foo()) == {"bar": None}
assert serialize(Foo, Foo(0)) == {"bar": 0}
