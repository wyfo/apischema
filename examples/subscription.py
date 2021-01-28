import asyncio
from typing import AsyncIterable

import graphql
from graphql import print_schema

from apischema.graphql import graphql_schema


def hello() -> str:
    return "world"


async def events() -> AsyncIterable[str]:
    yield "bonjour"
    yield "au revoir"


schema = graphql_schema(query=[hello], subscription=[events])
schema_str = """\
type Query {
  hello: String!
}

type Subscription {
  events: String!
}
"""
assert print_schema(schema) == schema_str


async def test():
    subscription = await graphql.subscribe(
        schema, graphql.parse("subscription {events}")
    )
    assert [event.data async for event in subscription] == [
        {"events": "bonjour"},
        {"events": "au revoir"},
    ]


asyncio.run(test())
