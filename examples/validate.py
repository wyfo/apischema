from dataclasses import dataclass, field

import pytest

from apischema import ValidationError, schema, validator
from apischema.validation import validate


@dataclass
class Foo:
    bar: int = field(metadata=schema(min=0, max=10))
    baz: int

    @validator
    def not_equal(self):
        if self.bar == self.baz:
            yield "bar cannot be equal to baz"


# validate don't validate constraints, but only validators
validate(Foo(-1, 0))

with pytest.raises(ValidationError) as err:
    validate(Foo(2, 2))
assert err.value.errors == [{"loc": [], "err": "bar cannot be equal to baz"}]
