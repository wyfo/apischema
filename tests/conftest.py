import sys

from apischema.graphql import relay
from apischema.graphql.relay import global_identification

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
