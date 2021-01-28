import asyncio
from dataclasses import dataclass
from typing import AsyncIterable

import graphql
from graphql import print_schema

from apischema.graphql import Subscription, graphql_schema


def hello() -> str:
    return "world"


async def events() -> AsyncIterable[str]:
    yield "bonjour"
    yield "au revoir"


@dataclass
class Message:
    body: str


# Message can also be used directly as a function
schema = graphql_schema(
    query=[hello],
    subscription=[Subscription(events, alias="messageReceived", resolver=Message)],
)
schema_str = """\
type Query {
  hello: String!
}

type Subscription {
  messageReceived: Message!
}

type Message {
  body: String!
}
"""
assert print_schema(schema) == schema_str


async def test():
    subscription = await graphql.subscribe(
        schema, graphql.parse("subscription {messageReceived {body}}")
    )
    assert [event.data async for event in subscription] == [
        {"messageReceived": {"body": "bonjour"}},
        {"messageReceived": {"body": "au revoir"}},
    ]


asyncio.run(test())
