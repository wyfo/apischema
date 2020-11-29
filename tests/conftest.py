import sys
from datetime import date, datetime
from typing import NewType

from apischema import deserializer, schema, serializer

if sys.version_info < (3, 7):
    Datetime = NewType("Datetime", str)
    schema(format="date-time")(Datetime)

    @deserializer
    def to_datetime(s: Datetime) -> datetime:
        return datetime.strptime(s, "%Y-%m-%d")

    @serializer
    def from_datetime(obj: datetime) -> Datetime:
        return Datetime(obj.strftime("%Y-%m-%dT%H:%M:%S"))

    Date = NewType("Date", str)
    schema(format="date")(Date)

    @deserializer
    def to_date(s: Date) -> date:
        return date.strptime(s, "%Y-%m-%d")

    @serializer
    def from_date(obj: date) -> Date:
        return Date(obj.strftime("%Y-%m-%d"))
