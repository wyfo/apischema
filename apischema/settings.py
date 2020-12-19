__all__ = [
    "additional_properties",
    "aliaser",
    "coercer",
    "coercion",
    "default_fallback",
    "deserialization",
    "json_schema_version",
    "serialization",
]

from typing import Any, Callable, Optional, Type, TypeVar, overload

from apischema import aliases
from apischema.deserialization import coercion as coercion_
from apischema.aliases import Aliaser
from apischema.cache import reset_cache
from apischema.conversions.visitor import (
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.json_schema import refs, schema, versions
from apischema.types import AnyType
from apischema.utils import to_camel_case

additional_properties = False
coercion: bool = False
default_fallback = False
json_schema_version = versions.JsonSchemaVersion.DRAFT_2019_09


@overload
def coercer() -> "coercion_.Coercer":
    ...


@overload
def coercer(func: "coercion_.Coercer") -> "coercion_.Coercer":
    ...


def coercer(func=None):
    if func is None:
        return coercion_._coercer
    elif func is coercion_.coerce:
        coercion_._coercer = func
    else:
        coercion_._coercer = coercion_.wrap_coercer(func)
        return func


DeserializationFunc = Callable[[Type, Optional[Any]], Optional[Deserialization]]
SerializationFunc = Callable[[Type, Optional[Any]], Optional[Serialization]]


@overload
def deserialization() -> DeserializationFunc:
    ...


@overload
def deserialization(func: DeserializationFunc) -> DeserializationFunc:
    ...


def deserialization(func=None):
    if func is None:
        return DeserializationVisitor._is_conversion
    else:
        DeserializationVisitor._is_conversion = staticmethod(func)
        reset_cache()
        return func


@overload
def serialization() -> SerializationFunc:
    ...


@overload
def serialization(func: SerializationFunc) -> SerializationFunc:
    ...


def serialization(func=None):
    if func is None:
        return SerializationVisitor._is_conversion
    else:
        SerializationVisitor._is_conversion = staticmethod(func)
        reset_cache()
        return func


AliaserFunc = TypeVar("AliaserFunc", bound=Aliaser)


@overload
def aliaser() -> Aliaser:
    ...


@overload
def aliaser(func: AliaserFunc) -> AliaserFunc:
    ...


@overload
def aliaser(*, camel_case: bool):
    ...


def aliaser(func=None, *, camel_case: bool = None):
    if camel_case is True:
        func = to_camel_case
    elif camel_case is False:
        func = lambda s: s  # noqa: E731
    if func is None:
        return aliases._global_aliaser
    else:
        aliases._global_aliaser = func
    return func


RefFunc = Callable[[AnyType], refs.Ref]


@overload
def default_ref() -> RefFunc:
    ...


@overload
def default_ref(func: RefFunc) -> RefFunc:
    ...


def default_ref(func=None):
    if func is None:
        return refs._default_ref
    else:
        refs._default_ref = func


SchemaFunc = Callable[[AnyType], Optional[schema.Schema]]


@overload
def default_schema() -> SchemaFunc:
    ...


@overload
def default_schema(func: SchemaFunc) -> SchemaFunc:
    ...


def default_schema(func=None):
    if func is None:
        return schema._default_schema
    else:
        schema._default_schema = func
        reset_cache()
