import asyncio
from dataclasses import dataclass
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


@dataclass
class Message:
    body: str


# Message can also be used directly as a function
schema = graphql_schema(query=[mandatory_query], subscription=[(events, Message)])
schema_str = """\
type Query {
  mandatoryQuery: Boolean!
}

type Subscription {
  message: Message!
}

type Message {
  body: String!
}
"""
assert print_schema(schema) == schema_str


async def test():
    subscription = await graphql.subscribe(
        schema, graphql.parse("subscription {message {body}}")
    )
    assert (await subscription.__anext__()).data == {"message": {"body": "bonjour"}}
    assert (await subscription.__anext__()).data == {"message": {"body": "au revoir"}}
    with raises(StopAsyncIteration):
        await subscription.__anext__()


asyncio.run(test())
