from dataclasses import dataclass
from uuid import UUID

import graphql
from graphql.utilities import print_schema

from apischema.graphql import graphql_schema, relay


@dataclass
class Ship(relay.Node[UUID]):  # Let's use an UUID for Ship id
    name: str

    @classmethod
    async def get_by_id(cls, id: UUID, info: graphql.GraphQLResolveInfo = None): ...


@dataclass
class Faction(relay.Node[int]):  # Nodes can have different id types
    name: str

    @classmethod
    def get_by_id(
        cls, id: int, info: graphql.GraphQLResolveInfo = None
    ) -> "Faction": ...


schema = graphql_schema(query=[relay.node], types=relay.nodes())
schema_str = """\
type Ship implements Node {
  id: ID!
  name: String!
}

interface Node {
  id: ID!
}

type Faction implements Node {
  id: ID!
  name: String!
}

type Query {
  node(id: ID!): Node!
}"""
assert print_schema(schema) == schema_str
