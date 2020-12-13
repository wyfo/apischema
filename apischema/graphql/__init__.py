__all__ = ["add_resolver", "graphql_schema", "interface", "resolver"]

from .interfaces import interface
from apischema.resolvers import add_resolver, resolver

try:
    from .builder import graphql_schema
except ImportError:
    raise ImportError(
        "GraphQL feature requires graphql-core library\n"
        "Run `pip install apischema[graphql]` to install it"
    )
