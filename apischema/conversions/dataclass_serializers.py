import dataclasses
from collections import ChainMap
from copy import copy
from inspect import getmembers
from itertools import chain
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.conversions.converters import extra_serializer, serializer
from apischema.conversions.metadata import conversions
from apischema.conversions.utils import Conversions
from apischema.dataclasses.cache import get_aggregate_serialization_fields
from apischema.fields import with_fields_set
from apischema.json_schema.refs import schema_ref
from apischema.typing import get_type_hints
from apischema.utils import MakeDataclassField

Metadata = Mapping[str, Any]


def _check_field(field: Any) -> str:
    if isinstance(field, dataclasses.Field):
        return field.name
    elif isinstance(field, str):
        return field
    elif isinstance(field, property):
        return field.fget.__name__
    else:
        raise TypeError("Serialization fields must be Field or str or property")


T = TypeVar("T")
FieldFactory = Callable[[T], Any]


def dataclass_serializer(
    cls: Type[T],
    ref: Optional[str] = None,
    *,
    include: Optional[Collection[Any]] = None,
    include_properties: bool = False,
    exclude: Collection[str] = (),
    override: Optional[Mapping[str, Optional[Metadata]]] = None,
    additional: Optional[
        Mapping[str, Union[FieldFactory[T], Tuple[FieldFactory[T], Conversions]]]
    ] = None,
    as_default_serializer: bool = False,
) -> Type:
    if override is None:
        override = {}
    override = {_check_field(field): metadata for field, metadata in override.items()}
    if include is not None:
        include = set(map(_check_field, include)) | override.keys()
    exclude = set(map(_check_field, exclude))
    fields, properties_fields = get_aggregate_serialization_fields(cls)
    new_fields: Dict[str, MakeDataclassField] = {}
    for field in chain(fields, properties_fields):
        if field.name in exclude or (include is not None and field.name not in include):
            continue
        new_field = copy(field.base_field)
        metadata = override.get(field.name)
        if metadata is not None:
            new_field.metadata = ChainMap(metadata, new_field.metadata)
        new_fields[field.name] = field.name, field.base_field.type, new_field
    for name, prop in getmembers(cls, lambda m: isinstance(m, property)):
        if name in exclude or (
            not include_properties and include is not None and name not in include
        ):
            continue
        assert isinstance(prop, property)
        types = get_type_hints(prop.fget, include_extras=True)
        try:
            new_fields[name] = name, types["return"]
        except KeyError:
            raise TypeError("Properties serialized must be typed") from None
    attributes_set = set(new_fields)
    factories: Dict[str, FieldFactory] = {}
    for name, factory in (additional or {}).items():
        attributes_set.discard(name)
        conv: Optional[Conversions]
        if isinstance(factory, tuple):
            factory, conv = factory
        else:
            conv = None
        factories[name] = factory
        new_field = dataclasses.field(metadata=conversions(serialization=conv))
        types = get_type_hints(factory, include_extras=True)
        try:
            new_fields[name] = name, types["return"], new_field
        except KeyError:
            raise TypeError("Additional field factories must be typed") from None
    attributes_list = list(attributes_set)  # for iteration performance
    serialized_class = with_fields_set(
        dataclasses.make_dataclass(f"{cls.__name__}Serializer", new_fields.values())
    )
    if ref is ...:
        raise TypeError("Dataclass serializer ref cannot be ...")
    schema_ref(ref)(serialized_class)
    register = serializer if as_default_serializer else extra_serializer

    def converter(obj):
        return serialized_class(
            **{name: getattr(obj, name) for name in attributes_list},
            **{name: factory(obj) for name, factory in factories.items()},
        )

    register(converter, cls, serialized_class)
    return serialized_class
