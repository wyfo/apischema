import os
import time
from dataclasses import dataclass
from datetime import datetime

from apischema import deserialize, serialize

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
