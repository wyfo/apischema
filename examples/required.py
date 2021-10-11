from dataclasses import dataclass, field

from pytest import raises

from apischema import ValidationError, deserialize
from apischema.metadata import required


@dataclass
class Foo:
    bar: int | None = field(default=None, metadata=required)


with raises(ValidationError) as err:
    deserialize(Foo, {})
assert err.value.errors == [{"loc": ["bar"], "msg": "missing property"}]
