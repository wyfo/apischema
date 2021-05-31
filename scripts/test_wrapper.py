# flake8: noqa
# type: ignore
import asyncio
import sys
import typing
from typing import *
from unittest.mock import MagicMock

from apischema.typing import Annotated, Literal, TypedDict

typing.Annotated, typing.Literal, typing.TypedDict = Annotated, Literal, TypedDict
if sys.version_info < (3, 9):

    class CollectionABC:
        def __getattribute__(self, name):
            return globals()[name] if name in globals() else MagicMock()

    sys.modules["collections.abc"] = CollectionABC()
    del CollectionABC


class Wrapper:
    def __init__(self, cls):
        self.cls = cls
        self.implem = cls.__origin__ or cls.__extra__  # extra in 3.6

    def __getitem__(self, item):
        return self.cls[item]

    def __call__(self, *args, **kwargs):
        return self.implem(*args, **kwargs)

    def __instancecheck__(self, instance):
        return isinstance(instance, self.implem)

    def __subclasscheck__(self, subclass):
        return issubclass(subclass, self.implem)


for cls in (Dict, List, Set, FrozenSet, Tuple, Type):  # noqa
    wrapper = Wrapper(cls)
    globals()[wrapper.implem.__name__] = wrapper

Set = AbstractSet

del Wrapper

if sys.version_info < (3, 7):
    asyncio.run = lambda coro: asyncio.get_event_loop().run_until_complete(coro)


def hack_relay_nodes():
    import graphql
    from apischema.graphql import relay

    class relay_wrapper:
        def __getattribute__(self, name):
            if name == "node":
                nodes = relay.nodes.copy()

                def node(
                    id: apischema.graphql.ID, info: graphql.GraphQLResolveInfo
                ) -> relay.Node:
                    from apischema.graphql.relay.global_identification import (
                        GlobalId,
                        InvalidGlobalId,
                        NotANode,
                    )

                    try:
                        node_key, id_ = id.split(":")
                    except ValueError:
                        raise InvalidGlobalId(id) from None
                    for cls in nodes:
                        if cls._node_key() == node_key:
                            return cls.get_by_id(
                                cls.id_from_global(GlobalId(id_, cls)), info
                            )
                    raise NotANode(node_key)

                return node
            else:
                return getattr(relay, name)

    import apischema

    apischema.graphql.relay = relay_wrapper()
    relay.nodes.clear()


hack_relay_nodes()
del hack_relay_nodes
