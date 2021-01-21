import os
import time
from dataclasses import dataclass
from datetime import datetime

from apischema import deserialize, serialize
from apischema.conversions import Conversion, identity

# Set UTC timezone for example
os.environ["TZ"] = "UTC"
time.tzset()


def datetime_from_timestamp(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp)


date = datetime(2017, 9, 2)
assert deserialize(datetime, 1504310400, conversions=datetime_from_timestamp) == date


@dataclass
class Foo:
    bar: int
    baz: int

    def sum(self) -> int:
        return self.bar + self.baz

    @property
    def diff(self) -> int:
        return int(self.bar - self.baz)


assert serialize(Foo(0, 1)) == {"bar": 0, "baz": 1}
assert serialize(Foo(0, 1), conversions=Foo.sum) == 1
assert serialize(Foo(0, 1), conversions=Foo.diff) == -1
# If a conversion is registered with serializer but you don't want to use it,
# you can use apischema.conversions.identity with source and target as your type
raw_foo = Conversion(identity, source=Foo, target=Foo)
assert serialize(Foo(0, 1), conversions=raw_foo) == {"bar": 0, "baz": 1}
