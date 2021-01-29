__all__ = [
    "Undefined",
    "UndefinedType",
    "Unsupported",
    "ValidationError",
    "alias",
    "deserialization",
    "deserialize",
    "deserializer",
    "properties",
    "reset_cache",
    "schema",
    "schema_ref",
    "serialize",
    "serialized",
    "serializer",
    "validator",
]


from . import (  # noqa: F401
    conversions,
    dataclasses,
    fields,
    json_schema,
    metadata,
    settings,
    skip,
    tagged_unions,
    validation,
)
from .aliases import alias
from .cache import reset_cache
from .conversions import deserializer, serializer
from .deserialization import deserialize
from .json_schema.refs import schema_ref
from .json_schema.schema import schema
from .metadata import properties
from .serialization import serialize
from .serialization.serialized_methods import serialized
from .utils import Undefined, UndefinedType
from .validation import ValidationError, validator
from .visitor import Unsupported

try:
    from . import graphql  # noqa: F401

    __all__.append("graphql")
except ImportError:
    pass


def __getattr__(name):
    if name == "graphql":
        raise AttributeError(
            "GraphQL feature requires graphql-core library\n"
            "Run `pip install apischema[graphql]` to install it"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def register_default_conversions():
    """Handle standard library + internal types"""
    from . import std_types  # noqa: F401

    deserializer(ValidationError.deserialize)
    serializer(ValidationError.serialize)


register_default_conversions()
