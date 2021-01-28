from dataclasses import dataclass, replace
from typing import AsyncIterable, Mapping, Optional

import graphql
from graphql.utilities import print_schema
from pytest import mark

from apischema import Undefined
from apischema.graphql import Subscription, graphql_schema

EVENTS = ["bonjour", "au revoir"]


@dataclass
class Event:
    name: str


def event_name(event: Event) -> str:
    return event.name


async def events(**kwargs) -> AsyncIterable[Event]:
    for event in EVENTS:
        yield Event(event)


async def anext(iterable):
    """Return the next item from an async iterator."""
    return await iterable.__anext__()


def wrap_event(event: str) -> Mapping[str, str]:
    return {"name": event}


def events2(event: Event, dummy: Optional[bool] = None) -> Event:
    return replace(event, name=event.name.capitalize())


def hello() -> str:
    return "world"


@mark.parametrize("alias", [None, "alias"])
@mark.parametrize("conversions", [None, event_name])
@mark.parametrize("error_handler", [Undefined, None])
@mark.parametrize("resolver", [None, events2])
@mark.asyncio
async def test_subscription(alias, conversions, error_handler, resolver):
    if alias is not None:
        sub_name = alias
    elif resolver is not None:
        sub_name = resolver.__name__
    else:
        sub_name = events.__name__
    if (alias, conversions, error_handler, resolver) == (None, None, Undefined, None):
        sub_op = events
    else:
        sub_op = Subscription(events, alias, conversions, None, error_handler, resolver)
    schema = graphql_schema(query=[hello], subscription=[sub_op], types=[Event])
    sub_field = sub_name
    if resolver is not None:
        sub_field += "(dummy: Boolean)"
    sub_field += f": {'String' if conversions else 'Event'}"
    if error_handler is Undefined:
        sub_field += "!"
    schema_str = """\
type Event {
  name: String!
}

type Query {
  hello: String!
}

type Subscription {
  %s
}
"""
    assert print_schema(schema) == schema_str % sub_field
    sub_query = sub_name
    if conversions is None:
        sub_query += "{name}"
    subscription = await graphql.subscribe(
        schema, graphql.parse("subscription {%s}" % sub_query)
    )
    result = EVENTS
    if resolver:
        result = [s.capitalize() for s in result]
    if not conversions:
        result = [{"name": s} for s in result]
    assert [ev.data async for ev in subscription] == [{sub_name: r} for r in result]
