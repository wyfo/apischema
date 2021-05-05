__all__ = [
    "Undefined",
    "UndefinedType",
    "Unsupported",
    "ValidationError",
    "alias",
    "dependent_required",
    "deserialization",
    "deserialize",
    "deserializer",
    "objects",
    "properties",
    "reset_cache",
    "schema",
    "schema_ref",
    "serialize",
    "serialized",
    "serializer",
    "type_name",
    "validator",
]


from . import (  # noqa: F401
    conversions,
    dataclasses,
    fields,
    json_schema,
    metadata,
    objects,
    settings,
    skip,
    tagged_unions,
    validation,
)
from .aliases import alias
from .cache import reset_cache
from .conversions import deserializer, serializer
from .dependencies import dependent_required
from .deserialization import deserialize
from .json_schema.schemas import schema
from .metadata import properties
from .serialization import serialize
from .serialization.serialized_methods import serialized
from .type_names import schema_ref, type_name
from .types import Undefined, UndefinedType
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
