from dataclasses import dataclass, field
from typing import Any

from apischema import serialize
from apischema.metadata import skip


@dataclass
class Foo:
    bar: Any = field(metadata=skip(serialization_if=lambda x: not x))
    baz: Any = field(default_factory=list, metadata=skip(serialization_default=True))


assert serialize(Foo(False, [])) == {}
