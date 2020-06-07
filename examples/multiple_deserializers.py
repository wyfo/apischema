import os
import time
from datetime import datetime

from apischema import deserialize, deserializer
from apischema.json_schema import deserialization_schema

# Set UTC timezone for example
os.environ["TZ"] = "UTC"
time.tzset()

# There is already `deserializer(datetime.fromisoformat, str, datetime) in apischema
# Let's add an other deserializer for datetime from a timestamp


@deserializer
def datetime_from_timestamp(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp)


assert deserialization_schema(datetime) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "anyOf": [{"type": "string", "format": "date-time"}, {"type": "integer"}],
}
assert (
    deserialize(datetime, "2019-10-13")
    == datetime(2019, 10, 13)
    == deserialize(datetime, 1570924800)
)
