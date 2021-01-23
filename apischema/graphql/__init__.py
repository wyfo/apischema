__all__ = ["ID", "Operation", "graphql_schema", "interface", "relay", "resolver"]


try:
    from .schema import ID, Operation, graphql_schema
    from .interfaces import interface
    from .resolvers import resolver
    from . import relay
except ImportError:
    raise ImportError(
        "GraphQL feature requires graphql-core library\n"
        "Run `pip install apischema[graphql]` to install it"
    )
