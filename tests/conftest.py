import sys
from datetime import date, datetime

from apischema import deserializer, schema, serializer, type_name

if sys.version_info < (3, 7):
    type_name("Datetime")(datetime)
    schema(format="date-time")(datetime)

    @deserializer
    def to_datetime(s: str) -> datetime:
        return datetime.strptime(s, "%Y-%m-%d")

    @serializer
    def from_datetime(obj: datetime) -> str:
        return obj.strftime("%Y-%m-%dT%H:%M:%S")

    type_name("Date")(date)
    schema(format="date")(date)

    @deserializer
    def to_date(s: str) -> date:
        return date.strptime(s, "%Y-%m-%d")

    @serializer
    def from_date(obj: date) -> str:
        return obj.strftime("%Y-%m-%d")
