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

from typing import Callable, Optional, Type, TypeVar, overload

from apischema import aliases
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import (
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dataclasses.cache import reset_dataclasses_cache
from apischema.deserialization import coercion as coercion_
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


DeserializationFunc = Callable[[Type, Optional[Conversions]], Optional[Deserialization]]
_DeserializationFunc = TypeVar("_DeserializationFunc", bound=DeserializationFunc)


@overload
def deserialization() -> DeserializationFunc:
    ...


@overload
def deserialization(func: _DeserializationFunc) -> _DeserializationFunc:
    ...


def deserialization(func=None):
    if func is None:
        return DeserializationVisitor.is_conversion
    else:
        DeserializationVisitor.is_conversion = staticmethod(func)
        return func


SerializationFunc = Callable[[Type, Optional[Conversions]], Optional[Serialization]]
_SerializationFunc = TypeVar("_SerializationFunc", bound=SerializationFunc)


@overload
def serialization() -> SerializationFunc:
    ...


@overload
def serialization(func: _SerializationFunc) -> _SerializationFunc:
    ...


def serialization(func=None):
    if func is None:
        return SerializationVisitor.is_conversion
    else:
        SerializationVisitor.is_conversion = staticmethod(func)
        return func


Aliaser = Callable[[str], str]
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
        aliases._global_aliaser = to_camel_case
    elif camel_case is False:
        aliases._global_aliaser = lambda s: s
    elif func is None:
        return aliases._global_aliaser
    else:
        aliases._global_aliaser = func
    reset_dataclasses_cache()
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
