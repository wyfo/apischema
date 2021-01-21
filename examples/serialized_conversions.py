import os
import time
from dataclasses import dataclass
from datetime import datetime

from apischema import serialize, serialized

# Set UTC timezone for example
os.environ["TZ"] = "UTC"
time.tzset()


def to_timestamp(d: datetime) -> int:
    return int(d.timestamp())


@dataclass
class Foo:
    @serialized(conversions=to_timestamp)
    def some_date(self) -> datetime:
        return datetime(1970, 1, 1)


assert serialize(Foo()) == {"some_date": 0}
