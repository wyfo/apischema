__all__ = [
    "NotNull",
    "Skip",
    "Unsupported",
    "ValidationError",
    "alias",
    "check_types",
    "conversions",
    "deserialization",
    "deserialize",
    "deserializer",
    "fields",
    "json_schema",
    "metadata",
    "properties",
    "schema",
    "schema_ref",
    "serialization",
    "serialize",
    "serializer",
    "settings",
    "validation",
    "validator",
]


from . import (
    conversions,
    deserialization,
    fields,
    json_schema,
    metadata,
    serialization,
    settings,
    validation,
)
from .aliases import alias
from .conversions import deserializer, serializer
from .deserialization import deserialize
from .json_schema.refs import schema_ref
from .json_schema.schema import schema
from .metadata import properties
from .serialization import serialize
from .type_checker import check_types
from .types import NotNull, Skip
from .validation import (
    ValidationError,
    validator,
)
from .visitor import Unsupported


def default_conversions():
    """Handle standard library + internal types"""
    from typing import Sequence
    from . import std_types  # noqa F401
    from .validation.errors import LocalizedError

    deserializer(ValidationError.deserialize, Sequence[LocalizedError], ValidationError)
    serializer(ValidationError.serialize, ValidationError)


default_conversions()
del default_conversions  # clean namespace
