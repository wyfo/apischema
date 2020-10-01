import os
import time
from dataclasses import dataclass, field
from datetime import datetime

from apischema import deserialize, serialize
from apischema.conversions import extra_deserializer, extra_serializer
from apischema.metadata import conversions

# Set UTC timezone for example
os.environ["TZ"] = "UTC"
time.tzset()

extra_deserializer(datetime.fromtimestamp, int, datetime)


@extra_serializer
def to_timestamp(d: datetime) -> int:
    return int(d.timestamp())


@dataclass
class Foo:
    some_date: datetime = field(metadata=conversions(int))
    # `conversions(int)` is equivalent to
    # `conversions(deserialization={datetime: int}, serialization={datetime: int})`
    other_date: datetime


assert deserialize(Foo, {"some_date": 0, "other_date": "2019-10-13"}) == Foo(
    datetime(1970, 1, 1), datetime(2019, 10, 13)
)
assert serialize(Foo(datetime(1970, 1, 1), datetime(2019, 10, 13))) == {
    "some_date": 0,
    "other_date": "2019-10-13T00:00:00",
}
