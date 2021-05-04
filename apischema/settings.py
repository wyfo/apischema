__all__ = [
    "additional_properties",
    "aliaser",
    "coercer",
    "coercion",
    "default_fallback",
    "default_schema",
    "default_type_name",
    "deserialization",
    "json_schema_version",
    "serialization",
]

import warnings
from typing import (
    Callable,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Type,
    TypeVar,
    Union,
    overload,
)

from apischema import aliases, type_names
from apischema.aliases import Aliaser
from apischema.cache import reset_cache
from apischema.conversions.conversions import Conversions
from apischema.conversions.visitor import DeserializationVisitor, SerializationVisitor
from apischema.json_schema import schemas, versions
from apischema.objects import ObjectField
from apischema.objects.visitor import ObjectVisitor
from apischema.type_names import TypeName
from apischema.types import AnyType
from apischema.utils import to_camel_case

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coercer

additional_properties = False
coercion: bool = False
default_fallback = False
exclude_unset = True
json_schema_version = versions.JsonSchemaVersion.DRAFT_2019_09

CoercerFunc = TypeVar("CoercerFunc", bound="Coercer")


@overload
def coercer() -> "Coercer":
    ...


@overload
def coercer(func: CoercerFunc) -> CoercerFunc:
    ...


def coercer(func: "Coercer" = None) -> "Coercer":
    from apischema.deserialization import coercion as c

    if func is None:
        return c._coercer
    elif func is c.coerce:
        c._coercer = func
    else:
        c._coercer = c.wrap_coercer(func)
    return func


DefaultConversions = Callable[[Type], Optional[Conversions]]
ConversionsFunc = TypeVar("ConversionsFunc", bound=DefaultConversions)


@overload
def deserialization() -> DefaultConversions:
    ...


@overload
def deserialization(func: ConversionsFunc) -> ConversionsFunc:
    ...


def deserialization(func: DefaultConversions = None) -> DefaultConversions:
    if func is None:
        return DeserializationVisitor._default_conversions  # type: ignore
    else:
        DeserializationVisitor._default_conversions = staticmethod(func)  # type: ignore
        reset_cache()
        return func


@overload
def serialization() -> DefaultConversions:
    ...


@overload
def serialization(func: ConversionsFunc) -> ConversionsFunc:
    ...


def serialization(func: DefaultConversions = None) -> DefaultConversions:
    if func is None:
        return SerializationVisitor._default_conversions
    else:
        SerializationVisitor._default_conversions = staticmethod(func)  # type: ignore
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


def aliaser(func: Aliaser = None, *, camel_case: bool = None):
    if camel_case is True:
        func = to_camel_case
    elif camel_case is False:
        func = lambda s: s  # noqa: E731
    if func is None:
        return aliases._global_aliaser
    else:
        aliases._global_aliaser = func  # type: ignore
    return func


DefaultTypeName = Callable[[AnyType], TypeName]
RefFunc = TypeVar("RefFunc", bound=Callable[[AnyType], Union[Optional[str], TypeName]])


@overload
def default_type_name() -> Callable[[AnyType], TypeName]:
    ...


@overload
def default_type_name(func: RefFunc) -> RefFunc:
    ...


def default_type_name(func=None):
    if func is None:
        return type_names._default_type_name
    else:

        def wrapper(tp: AnyType) -> TypeName:
            name = func(tp)
            return name if isinstance(name, TypeName) else TypeName(name, name)

        type_names._default_type_name = wrapper
        reset_cache()
        return func


def default_ref(func=None):
    warnings.warn(
        "default_ref if deprecated, use default_type_name instead", DeprecationWarning
    )


DefaultSchema = Callable[[AnyType], Optional[schemas.Schema]]
SchemaFunc = TypeVar("SchemaFunc", bound=DefaultSchema)


@overload
def default_schema() -> DefaultSchema:
    ...


@overload
def default_schema(func: SchemaFunc) -> SchemaFunc:
    ...


def default_schema(func: DefaultSchema = None) -> DefaultSchema:
    if func is None:
        return schemas._default_schema
    else:
        schemas._default_schema = func  # type: ignore
        reset_cache()
        return func


DefaultFields = Callable[[AnyType], Optional[Sequence[ObjectField]]]
FieldsFunc = TypeVar("FieldsFunc", bound=DefaultFields)


@overload
def default_object_fields() -> DefaultFields:
    ...


@overload
def default_object_fields(func: FieldsFunc) -> FieldsFunc:
    ...


def default_object_fields(func: DefaultFields = None) -> DefaultFields:
    if func is None:
        return ObjectVisitor._object_fields
    else:
        ObjectVisitor._object_fields = staticmethod(func)  # type: ignore
        reset_cache()
        return func
