from dataclasses import dataclass, field
from typing import Optional

from pytest import raises

from apischema import ValidationError, deserialize, serialize
from apischema.metadata import required


@dataclass
class Foo:
    bar: Optional[int] = field(default=None, metadata=required)


with raises(ValidationError) as err:
    deserialize(Foo, {})
assert serialize(err.value) == [{"loc": ["bar"], "err": ["missing property"]}]
