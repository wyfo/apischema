from dataclasses import dataclass
from typing import Optional, TypeVar

from graphql import print_schema

from apischema.graphql import graphql_schema, relay, resolver

Cursor = int
Node = TypeVar("Node")
Edge = TypeVar("Edge", bound=relay.Edge)


@dataclass
class MyConnection(relay.Connection[Node, Cursor, Edge]):
    connection_field: bool


@dataclass
class MyEdge(relay.Edge[Node, Cursor]):
    edge_field: int | None


Connection = MyConnection[Node, MyEdge[Node]]


@dataclass
class Ship:
    name: str


@dataclass
class Faction:
    @resolver
    def ships(
        self, first: int | None, after: Cursor | None
    ) -> Connection[Optional[Ship]] | None: ...


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
  connectionField: Boolean!
}

type ShipEdge {
  node: Ship
  cursor: Int!
  edgeField: Int
}

type Ship {
  name: String!
}

type PageInfo {
  hasPreviousPage: Boolean!
  hasNextPage: Boolean!
  startCursor: Int
  endCursor: Int
}"""
assert print_schema(schema) == schema_str
