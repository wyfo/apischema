from dataclasses import dataclass

import graphql

from apischema import serialize
from apischema.graphql import graphql_schema, relay


@dataclass
class Faction(relay.Node[int]):
    name: str

    @classmethod
    def get_by_id(cls, id: int, info: graphql.GraphQLResolveInfo = None) -> "Faction":
        return [Faction(0, "Empire"), Faction(1, "Rebels")][id]


schema = graphql_schema(query=[relay.node], types=relay.nodes)
some_global_id = Faction.get_by_id(0).global_id  # Let's pick a global id ...
assert some_global_id == relay.GlobalId("0", Faction)
query = """
query factionName($id: ID!) {
    node(id: $id) {
        ... on Faction {
            name
        }
    }
}
"""
assert graphql.graphql_sync(  # ... and use it in a query
    schema, query, variable_values={"id": serialize(some_global_id)}
).data == {"node": {"name": "Empire"}}
