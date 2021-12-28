import sys
from datetime import date, datetime

from apischema import deserializer, schema, serializer, type_name
from apischema.graphql import relay
from apischema.graphql.relay import global_identification

if sys.version_info < (3, 7):
    type_name("Datetime")(datetime)
    schema(format="date-time")(datetime)

    @deserializer
    def to_datetime(s: str) -> datetime:
        if "T" not in s:
            return datetime.strptime(s, "%Y-%m-%d")
        elif "." not in s:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        else:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")

    @serializer
    def from_datetime(obj: datetime) -> str:
        return obj.strftime("%Y-%m-%dT%H:%M:%S")

    type_name("Date")(date)
    schema(format="date")(date)

    @deserializer
    def to_date(s: str) -> date:
        return datetime.strptime(s, "%Y-%m-%d").date()

    @serializer
    def from_date(obj: date) -> str:
        return obj.strftime("%Y-%m-%d")


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
