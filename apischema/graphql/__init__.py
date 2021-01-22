__all__ = ["ID", "Operation", "graphql_schema", "interface", "resolver"]


try:
    from .schema import ID, Operation, graphql_schema
    from .interfaces import interface
    from .resolvers import resolver
except ImportError:
    raise ImportError(
        "GraphQL feature requires graphql-core library\n"
        "Run `pip install apischema[graphql]` to install it"
    )
