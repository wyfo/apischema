from dataclasses import dataclass, field

from apischema import alias, schema
from apischema.metadata import required


@dataclass
class Foo:
    bar: int = field(
        default=0,
        metadata=alias("foo_bar") | schema(title="foo! bar!", min=0, max=42) | required,
    )
