from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Collection, Dict, Mapping, Optional

import graphql

from apischema.aliases import Aliaser
from apischema.conversions import Conversions
from apischema.conversions.dataclass_model import DataclassModelWrapper
from apischema.conversions.visitor import SerializationVisitor
from apischema.deserialization import deserialize
from apischema.resolvers import Resolver
from apischema.serialization import (
    COLLECTION_TYPE_SET,
    MAPPING_TYPE_SET,
    PRIMITIVE_TYPES_SET,
    serialize,
)
from apischema.types import PRIMITIVE_TYPES
from apischema.validation.errors import ValidationError
from apischema.visitor import Unsupported


def partial_serialize(
    obj: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
) -> Any:
    assert aliaser is not None
    cls = obj.__class__
    if cls in PRIMITIVE_TYPES_SET:
        return obj
    if cls in COLLECTION_TYPE_SET:
        return [
            partial_serialize(elt, conversions=conversions, aliaser=aliaser)
            for elt in obj
        ]
    if cls in MAPPING_TYPE_SET:
        return serialize(
            obj, conversions=conversions, aliaser=aliaser, exclude_unset=False
        )
    target = None
    if conversions is not None:
        try:
            target = conversions[cls]
        except KeyError:
            pass
    conversion = SerializationVisitor._is_conversion(cls, target)
    if conversion is not None:
        _, (converter, sub_conversions) = conversion
        if isinstance(target, DataclassModelWrapper):
            return obj
        return partial_serialize(
            converter(obj), conversions=sub_conversions, aliaser=aliaser
        )
    if is_dataclass(cls):
        return obj
    if issubclass(cls, Enum):
        return serialize(obj.value, aliaser=aliaser, exclude_unset=False)
    if isinstance(obj, PRIMITIVE_TYPES):
        return obj
    if isinstance(obj, Mapping):
        return serialize(obj, aliaser=aliaser, exclude_unset=False)
    if isinstance(obj, Collection):
        return [partial_serialize(elt, aliaser=aliaser) for elt in obj]
    if issubclass(cls, tuple) and hasattr(cls, "_fields"):
        return obj
    raise Unsupported(cls)


INFO_TYPES = {graphql.GraphQLResolveInfo, Optional[graphql.GraphQLResolveInfo]}


def resolver_resolve(
    resolver: Resolver, aliaser: Aliaser, error_as_null: bool, serialized: bool = True
) -> Callable:
    parameters = resolver.parameters
    types = resolver.types
    info_param = next((p.name for p in parameters if types[p.name] in INFO_TYPES), None)
    arg_types = [(p.name, types[p.name]) for p in parameters if p.name != info_param]
    func = resolver.wrapper
    serialize_result: Callable[[Any], Any]
    if not serialized:

        def serialize_result(result):
            return result

    elif resolver.is_async:

        async def serialize_result(result: Awaitable):
            return partial_serialize(
                await result, conversions=resolver.conversions, aliaser=aliaser
            )

    else:

        def serialize_result(result):
            return partial_serialize(
                result, conversions=resolver.conversions, aliaser=aliaser
            )

    def resolve(self, info, **kwargs):
        errors: Dict[str, ValidationError] = {}
        for arg_name, arg_type in arg_types:
            if arg_name in kwargs:
                try:
                    kwargs[arg_name] = deserialize(arg_type, kwargs[arg_name])
                except ValidationError as err:
                    errors[aliaser(arg_name)] = err
        if errors:
            raise TypeError(serialize(ValidationError(children=errors)))
        if info_param:
            kwargs[info_param] = info
        try:
            return serialize_result(func(self, **kwargs))
        except Exception:
            if error_as_null:
                return None
            else:
                raise

    return resolve
