import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import NewType

from apischema import deserialize, serialize
from apischema.conversions import extra_deserializer, extra_serializer

# Set UTC timezone for example
os.environ["TZ"] = "UTC"
time.tzset()


@extra_deserializer
def datetime_from_timestamp(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp)


date = datetime(2017, 9, 2)
assert deserialize(datetime, 1504310400, conversions={datetime: int}) == date

Diff = NewType("Diff", int)


@dataclass
class Foo:
    bar: int
    baz: int

    @extra_serializer
    def summary(self) -> int:
        return self.bar + self.baz

    # You can use NewType to disambiguate conversion to int
    @extra_serializer
    def diff(self) -> Diff:
        return Diff(self.bar - self.baz)


assert serialize(Foo(0, 1)) == {"bar": 0, "baz": 1}
assert serialize(Foo(0, 1), conversions={Foo: Foo}) == {"bar": 0, "baz": 1}
assert serialize(Foo(0, 1), conversions={Foo: int}) == 1
assert serialize(Foo(0, 1), conversions={Foo: Diff}) == -1
