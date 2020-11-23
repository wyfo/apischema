from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterable, Mapping

from graphql import (
    GraphQLArgument,
    GraphQLBoolean,
    GraphQLField,
    GraphQLInt,
    GraphQLList,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLString,
    graphql_sync,
    parse,
    print_schema,
    subscribe,
)
from pytest import mark

from apischema import schema_ref
from apischema.graphql.builder import graphql_schema
from apischema.graphql.interfaces import interface


@interface
@dataclass
class A:
    a: int


@dataclass
class B(A):
    b: str
    pass


schema_ref("StrMapping")(Mapping[str, Any])


class E(Enum):
    a = "PLOP"


def plop() -> E:
    return E.a


def test():
    schema = graphql_schema([plop])
    print(print_schema(schema))
    print(graphql_sync(schema, "{plop}"))


@dataclass
class Event:
    name: str


async def events() -> AsyncIterable[Event]:
    for event in ("bonjour", "au revoir"):
        yield Event(event)


async def anext(iterable):
    """Return the next item from an async iterator."""
    return await iterable.__anext__()


@mark.asyncio
async def test2():
    schema = graphql_schema([plop], subscription=[events])
    print(print_schema(schema))
    subscription = await subscribe(schema, parse("subscription {events{name}}"))
    async for event in subscription:
        print(event)


@mark.asyncio
async def test_plop():
    EmailType = GraphQLObjectType(
        "Email",
        {
            "from": GraphQLField(GraphQLString),
            "subject": GraphQLField(GraphQLString),
            "message": GraphQLField(GraphQLString),
            "unread": GraphQLField(GraphQLBoolean),
        },
    )
    InboxType = GraphQLObjectType(
        "Inbox",
        {
            "total": GraphQLField(
                GraphQLInt, resolve=lambda inbox, _info: len(inbox["emails"])
            ),
            "unread": GraphQLField(
                GraphQLInt,
                resolve=lambda inbox, _info: sum(
                    1 for email in inbox["emails"] if email["unread"]
                ),
            ),
            "emails": GraphQLField(GraphQLList(EmailType)),
        },
    )
    EmailEventType = GraphQLObjectType(
        "EmailEvent",
        {"email": GraphQLField(EmailType), "inbox": GraphQLField(InboxType)},
    )
    QueryType = GraphQLObjectType("Query", {"inbox": GraphQLField(InboxType)})

    def email_schema_with_resolvers(subscribe_fn=None, resolve_fn=None):
        return GraphQLSchema(
            QueryType,
            subscription=GraphQLObjectType(
                "Subscription",
                {
                    "importantEmail": GraphQLField(
                        EmailEventType,
                        args={"priority": GraphQLArgument(GraphQLInt)},
                        resolve=resolve_fn,
                        subscribe=subscribe_fn,
                    )
                },
            ),
        )

    async def subscribe_fn(_data, _info):
        yield {"email": {"subject": "Hello"}}
        yield {"email": {"subject": "Goodbye"}}
        yield {"email": {"subject": "Bonjour"}}

    def resolve_fn(event, _info):
        if event["email"]["subject"] == "Goodbye":
            raise RuntimeError("Never leave")
        return event

    erroring_email_schema = email_schema_with_resolvers(subscribe_fn, resolve_fn)
    print(print_schema(erroring_email_schema))

    subscription = await subscribe(
        erroring_email_schema,
        parse(
            """
            subscription {
              importantEmail {
                email {
                  subject
                }
              }
            }
            """
        ),
    )

    payload1 = await anext(subscription)
    assert payload1 == ({"importantEmail": {"email": {"subject": "Hello"}}}, None)

    # An error in execution is presented as such.
    payload2 = await anext(subscription)
    assert payload2 == (
        {"importantEmail": None},
        [
            {
                "message": "Never leave",
                "locations": [(3, 15)],
                "path": ["importantEmail"],
            }
        ],
    )

    # However that does not close the response event stream. Subsequent events are
    # still executed.
    payload3 = await anext(subscription)
    assert payload3 == ({"importantEmail": {"email": {"subject": "Bonjour"}}}, None)
