import sys
from datetime import date, datetime
from typing import NewType

from apischema import deserializer, schema, serializer
from apischema.graphql import relay
from apischema.graphql.relay import global_identification

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


relay.Node._node_key = classmethod(  # type: ignore
    lambda cls: f"{cls.__module__}.{cls.__name__}"
)


nodes_wrapped = relay.nodes


def nodes():
    exclude = set()
    for node_cls in global_identification._tmp_nodes:
        # The module currently imported should not have schema defined
        if hasattr(sys.modules[node_cls.__module__], "schema"):
            exclude.add(node_cls)
    return [cls for cls in nodes_wrapped() if cls not in exclude]


relay.nodes = nodes
