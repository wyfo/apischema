from dataclasses import dataclass

from graphql.utilities import print_schema

from apischema.graphql import graphql_schema, relay


@dataclass
class Ship: ...


@dataclass
class Faction: ...


@dataclass
class IntroduceShip(relay.Mutation):
    ship: Ship
    faction: Faction

    @staticmethod
    def mutate(
        # mut_id is required because no default value
        faction_id: str,
        ship_name: str,
        mut_id: relay.ClientMutationId,
    ) -> "IntroduceShip": ...


def hello() -> str:
    return "world"


schema = graphql_schema(query=[hello], mutation=relay.mutations())
# clientMutationId field becomes non nullable in introduceShip types
schema_str = """\
type Query {
  hello: String!
}

type Mutation {
  introduceShip(input: IntroduceShipInput!): IntroduceShipPayload!
}

type IntroduceShipPayload {
  ship: Ship!
  faction: Faction!
  clientMutationId: String!
}

type Ship

type Faction

input IntroduceShipInput {
  factionId: String!
  shipName: String!
  clientMutationId: String!
}"""
assert print_schema(schema) == schema_str
