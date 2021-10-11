from dataclasses import dataclass
from typing import Optional, TypeVar

import graphql
from graphql.utilities import print_schema

from apischema.graphql import graphql_schema, relay, resolver

Cursor = int  # let's use an integer cursor in all our connection
Node = TypeVar("Node")
Connection = relay.Connection[Node, Cursor, relay.Edge[Node, Cursor]]
# Connection can now be used just like Connection[Ship] or Connection[Faction | None]


@dataclass
class Ship:
    name: str


@dataclass
class Faction:
    @resolver
    def ships(
        self, first: int | None, after: Cursor | None
    ) -> Connection[Optional[Ship]] | None:
        edges = [relay.Edge(Ship("X-Wing"), 0), relay.Edge(Ship("B-Wing"), 1)]
        return Connection(edges, relay.PageInfo.from_edges(edges))


def faction() -> Faction | None:
    return Faction()


schema = graphql_schema(query=[faction])
schema_str = """\
type Query {
  faction: Faction
}

type Faction {
  ships(first: Int, after: Int): ShipConnection
}

type ShipConnection {
  edges: [ShipEdge]
  pageInfo: PageInfo!
}

type ShipEdge {
  node: Ship
  cursor: Int!
}

type Ship {
  name: String!
}

type PageInfo {
  hasPreviousPage: Boolean!
  hasNextPage: Boolean!
  startCursor: Int
  endCursor: Int
}
"""
assert print_schema(schema) == schema_str
query = """
{
    faction {
        ships {
            pageInfo {
                endCursor
                hasNextPage
            }
            edges {
                cursor
                node {
                    name
                }
            }
        }
    }
}
"""
assert graphql.graphql_sync(schema, query).data == {
    "faction": {
        "ships": {
            "pageInfo": {"endCursor": 1, "hasNextPage": False},
            "edges": [
                {"cursor": 0, "node": {"name": "X-Wing"}},
                {"cursor": 1, "node": {"name": "B-Wing"}},
            ],
        }
    }
}
