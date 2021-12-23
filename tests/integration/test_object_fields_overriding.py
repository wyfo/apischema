import sys
from dataclasses import dataclass, replace
from typing import Optional

import pytest

from apischema import ValidationError, deserialize, serialize
from apischema.metadata import none_as_undefined
from apischema.objects import object_fields, set_object_fields


@dataclass
class Foo:
    bar: Optional[str] = None


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="dataclasses.replace bug with InitVar"
)
def test_object_fields_overriding():
    set_object_fields(Foo, [])
    assert serialize(Foo, Foo()) == {}
    set_object_fields(
        Foo,
        [
            replace(f, metadata=none_as_undefined | f.metadata)
            for f in object_fields(Foo, default=None).values()
        ],
    )
    assert serialize(Foo, Foo()) == {}
    with pytest.raises(ValidationError):
        deserialize(Foo, {"bar": None})
