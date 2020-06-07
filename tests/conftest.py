import sys
from datetime import datetime
from typing import NewType

from apischema import deserializer, schema, serializer

if sys.version_info < (3, 7):
    DateTime = NewType("DateTime", str)
    schema(format="date-time")(DateTime)

    @deserializer
    def to_datetime(s: DateTime) -> datetime:
        return datetime.strptime(s, "%Y-%m-%d")

    @serializer
    def from_datetime(obj: datetime) -> DateTime:
        return DateTime(obj.strftime("%Y-%m-%dT%H:%M:%S"))
