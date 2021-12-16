__all__ = [
    "PassThroughOptions",
    "Undefined",
    "UndefinedType",
    "Unsupported",
    "ValidationError",
    "alias",
    "dependent_required",
    "deserialization_method",
    "deserialize",
    "deserializer",
    "identity",
    "order",
    "properties",
    "schema",
    "schema_ref",
    "serialization_default",
    "serialization_method",
    "serialize",
    "serialized",
    "serializer",
    "settings",
    "type_name",
    "validator",
]

import warnings

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
from .ordering import order
from .schemas import schema
from .serialization import (
    PassThroughOptions,
    serialization_default,
    serialization_method,
    serialize,
)
from .serialization.serialized_methods import serialized
from .settings import settings
from .type_names import schema_ref, type_name
from .types import Undefined, UndefinedType
from .utils import identity
from .validation import ValidationError, validator
from .visitor import Unsupported

try:
    import graphql as _gql

    if _gql.__version__.startswith("2."):
        warnings.warn(
            f"graphql-core version {_gql.__version__} is incompatible with apischema;\n"
            "GraphQL schema generation is thus not available."
        )
    else:
        from . import graphql  # noqa: F401

        __all__.append("graphql")
    del _gql
except ImportError:
    pass


def __getattr__(name):
    if name == "graphql":
        raise AttributeError(
            "GraphQL feature requires graphql-core library\n"
            "Run `pip install apischema[graphql]` to install it"
        )
    if name == "skip":
        warnings.warn("apischema.skip module is deprecated")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def register_default_conversions():
    """Handle standard library + internal types"""
    from . import std_types  # noqa: F401

    deserializer(ValidationError.from_errors)
    serializer(ValidationError.errors)


register_default_conversions()
del register_default_conversions
