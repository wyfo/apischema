import asyncio
from typing import AsyncIterable

import graphql
from graphql import print_schema
from pytest import raises

from apischema.graphql import graphql_schema


# GraphQL schema requires a non-empty query
def mandatory_query() -> bool:
    return True


async def events() -> AsyncIterable[str]:
    yield "bonjour"
    yield "au revoir"


schema = graphql_schema(query=[mandatory_query], subscription=[events])
schema_str = """\
type Query {
  mandatoryQuery: Boolean!
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
    assert (await subscription.__anext__()).data == {"events": "bonjour"}
    assert (await subscription.__anext__()).data == {"events": "au revoir"}
    with raises(StopAsyncIteration):
        await subscription.__anext__()


asyncio.run(test())
