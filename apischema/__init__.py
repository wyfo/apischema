__all__ = [
    "Undefined",
    "UndefinedType",
    "Unsupported",
    "ValidationError",
    "alias",
    "dependent_required",
    "deserialization_method",
    "deserialize",
    "deserializer",
    "properties",
    "schema",
    "schema_ref",
    "serialization_method",
    "serialize",
    "serialized",
    "serializer",
    "settings",
    "type_name",
    "validator",
]


from . import (  # noqa: F401
    cache,
    conversions,
    dataclasses,
    fields,
    json_schema,
    metadata,
    objects,
    skip,
    tagged_unions,
    validation,
)
from .aliases import alias
from .conversions import deserializer, serializer
from .dependencies import dependent_required
from .deserialization import deserialization_method, deserialize
from .metadata import properties
from .schemas import schema
from .serialization import serialization_method, serialize
from .serialization.serialized_methods import serialized
from .settings import settings
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
del register_default_conversions
