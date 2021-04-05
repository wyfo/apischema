from dataclasses import dataclass, field
from typing import Annotated

from apischema import alias, schema
from apischema.metadata import required


@dataclass
class Foo:
    bar: int = field(
        default=0,
        metadata=alias("foo_bar") | schema(title="foo! bar!", min=0, max=42) | required,
    )
    baz: Annotated[
        int, alias("foo_baz"), schema(title="foo! baz!", min=0, max=32), required
    ] = 0
    # pipe `|` operator can also be used in Annotated
