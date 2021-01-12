__all__ = ["Operation", "graphql_schema", "interface", "resolver"]


try:
    from .builder import Operation, graphql_schema
    from .interfaces import interface
    from .resolvers import resolver
except ImportError:
    raise ImportError(
        "GraphQL feature requires graphql-core library\n"
        "Run `pip install apischema[graphql]` to install it"
    )
