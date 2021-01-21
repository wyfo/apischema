import os
import time
from dataclasses import dataclass, field
from datetime import datetime

from apischema import deserialize, serialize
from apischema.conversions import Conversion
from apischema.metadata import conversion

# Set UTC timezone for example
os.environ["TZ"] = "UTC"
time.tzset()

from_timestamp = Conversion(datetime.fromtimestamp, source=int, target=datetime)


def to_timestamp(d: datetime) -> int:
    return int(d.timestamp())


@dataclass
class Foo:
    some_date: datetime = field(metadata=conversion(from_timestamp, to_timestamp))
    other_date: datetime


assert deserialize(Foo, {"some_date": 0, "other_date": "2019-10-13"}) == Foo(
    datetime(1970, 1, 1), datetime(2019, 10, 13)
)
assert serialize(Foo(datetime(1970, 1, 1), datetime(2019, 10, 13))) == {
    "some_date": 0,
    "other_date": "2019-10-13T00:00:00",
}
