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
    def mutate(faction_id: str, ship_name: str) -> "IntroduceShip": ...


def hello() -> str:
    return "world"


schema = graphql_schema(query=[hello], mutation=relay.mutations())
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
  clientMutationId: String
}

type Ship

type Faction

input IntroduceShipInput {
  factionId: String!
  shipName: String!
  clientMutationId: String
}"""
assert print_schema(schema) == schema_str
