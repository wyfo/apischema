__all__ = [
    "Undefined",
    "UndefinedType",
    "Unsupported",
    "ValidationError",
    "alias",
    "conversions",
    "dataclasses",
    "deserialization",
    "deserialize",
    "deserializer",
    "fields",
    "graphql_schema",
    "interface",
    "json_schema",
    "metadata",
    "properties",
    "reset_cache",
    "resolver",
    "resolvers",
    "schema",
    "schema_ref",
    "serialization",
    "serialize",
    "serialized",
    "serializer",
    "settings",
    "skip",
    "validation",
    "validator",
]


from . import (
    conversions,
    dataclasses,
    fields,
    json_schema,
    metadata,
    resolvers,
    serialization,
    settings,
    skip,
    validation,
)
from .aliases import alias
from .cache import reset_cache
from .conversions import deserializer, serializer
from .deserialization import deserialize
from .json_schema.refs import schema_ref
from .json_schema.schema import schema
from .metadata import properties
from .resolvers import resolver
from .serialization import serialize, serialized
from .utils import Undefined, UndefinedType
from .graphql.interfaces import interface
from .graphql.builder import graphql_schema
from .validation import (
    ValidationError,
    validator,
)
from .visitor import Unsupported


def default_conversions():
    """Handle standard library + internal types"""
    from typing import Sequence
    from . import std_types  # noqa: F401
    from .validation.errors import LocalizedError

    deserializer(ValidationError.deserialize, Sequence[LocalizedError], ValidationError)
    serializer(ValidationError.serialize, ValidationError)


default_conversions()
del default_conversions  # clean namespace
