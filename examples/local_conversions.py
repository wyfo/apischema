import os
import time
from dataclasses import dataclass
from datetime import datetime

from apischema import serialize

# Set UTC timezone for example
os.environ["TZ"] = "UTC"
time.tzset()


def to_timestamp(d: datetime) -> int:
    return int(d.timestamp())


@dataclass
class Foo:
    bar: datetime


# timestamp conversion is not applied on Foo field because it's discarded
# when encountering Foo
assert serialize(Foo, Foo(datetime(2019, 10, 13)), conversions=to_timestamp) == {
    "bar": "2019-10-13T00:00:00"
}

# timestamp conversion is applied on every member of list
assert serialize(list[datetime], [datetime(1970, 1, 1)], conversions=to_timestamp) == [
    0
]
