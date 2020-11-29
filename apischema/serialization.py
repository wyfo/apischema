__all__ = ["add_serialized", "serialize", "serialized"]

from dataclasses import dataclass, is_dataclass
from enum import Enum
from inspect import Parameter, iscoroutinefunction
from typing import (
    Any,
    Callable,
    Collection,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
)

from apischema import settings
from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.dataclass_model import DataclassModelWrapper, get_model
from apischema.conversions.metadata import get_field_conversions
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import SerializationVisitor
from apischema.dataclass_utils import dataclass_types_and_fields, get_alias
from apischema.fields import FIELDS_SET_ATTR, fields_set
from apischema.metadata.keys import SKIP_METADATA, check_metadata, is_aggregate_field
from apischema.resolvers import (
    Resolver,
    ResolverDescriptor,
    add_resolver,
    get_resolvers,
    resolver,
)
from apischema.types import COLLECTION_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES
from apischema.utils import Undefined, typed_wraps
from apischema.visitor import Unsupported

PRIMITIVE_TYPES_SET = set(PRIMITIVE_TYPES)
COLLECTION_TYPE_SET = set(COLLECTION_TYPES)
MAPPING_TYPE_SET = set(MAPPING_TYPES)

SerializationMethod = Callable[[Any, Callable], Any]


@dataclass
class SerializationField:
    name: str
    method: SerializationMethod


@cache
def serialization_fields(
    cls: Type, aliaser: Aliaser
) -> Tuple[
    Sequence[Tuple[str, SerializationField]],
    Sequence[SerializationField],
    Sequence[Tuple[str, SerializationMethod]],
]:
    types, fields, _ = dataclass_types_and_fields(cls)  # type: ignore
    normal_fields, aggregate_fields, serialized_fields = [], [], []
    for field in fields:
        if SKIP_METADATA in field.metadata:
            continue
        check_metadata(field)
        field_type = types[field.name]
        method: Callable
        conversions = get_field_conversions(field, field_type)
        if conversions is not None:
            if conversions.serializer is None:

                def method(
                    obj: Any,
                    _serialize: Callable,
                    conversions=conversions.serialization,  # type: ignore
                ) -> Any:
                    return _serialize(obj, conversions=conversions)

            else:
                _, (converter, sub_conversions) = conversions.serialization_conversion(
                    field_type
                )

                def method(
                    obj: Any, _serialize: Callable, conversions=sub_conversions
                ) -> Any:
                    return _serialize(converter(obj), conversions=conversions)

        elif field_type in PRIMITIVE_TYPES_SET:
            method = lambda obj, _: obj  # noqa: E731
        else:
            method = lambda obj, _serialize: _serialize(obj)  # noqa: E731
        field2 = SerializationField(field.name, method)
        if is_aggregate_field(field):
            aggregate_fields.append(field2)
        else:
            normal_fields.append((aliaser(get_alias(field)), field2))
    # TODO handle dataclass model feature
    for name, resolver in get_serialized_resolvers(cls).items():  # noqa: F402

        def method(
            obj: Any,
            _serialize: Callable,
            func=resolver.wrapper,
            conversions=resolver.conversions,
        ) -> Any:
            return _serialize(func(obj), conversions=conversions)

        serialized_fields.append((aliaser(name), method))

    return normal_fields, aggregate_fields, serialized_fields


def serialize(
    obj: Any,
    *,
    conversions: Conversions = None,
    aliaser: Aliaser = None,
    exclude_unset: bool = True,
) -> Any:
    if aliaser is None:
        aliaser = settings.aliaser()
    is_conversion = SerializationVisitor._is_conversion

    def _serialize(
        obj: Any,
        *,
        conversions: Optional[Conversions] = None,
    ) -> Any:
        assert aliaser is not None
        cls = obj.__class__
        if cls in PRIMITIVE_TYPES_SET:
            return obj
        if cls in COLLECTION_TYPE_SET:
            return [_serialize(elt, conversions=conversions) for elt in obj]
        if cls in MAPPING_TYPE_SET:
            return {
                _serialize(key, conversions=conversions): _serialize(
                    value, conversions=conversions
                )
                for key, value in obj.items()
            }
        target = None
        if conversions is not None:
            try:
                target = conversions[cls]
            except KeyError:
                pass
        conversion = is_conversion(cls, target)
        if conversion is not None:
            target, (converter, sub_conversions) = conversion
            if isinstance(target, DataclassModelWrapper):
                cls = get_model(target.cls, target.model)
            else:
                # TODO Maybe add exclude_unset parameter to serializers
                return _serialize(converter(obj), conversions=sub_conversions)
        if is_dataclass(cls):
            fields, aggregate_fields, serialized_fields = serialization_fields(
                cls, aliaser
            )
            if exclude_unset and hasattr(obj, FIELDS_SET_ATTR):
                fields_set_ = fields_set(obj)
                fields = [(a, f) for (a, f) in fields if f.name in fields_set_]
                aggregate_fields = [
                    f for f in aggregate_fields if f.name in fields_set_
                ]
            result = {}
            # properties before normal fields to avoid overloading a field with property
            for field in aggregate_fields:
                attr = getattr(obj, field.name)
                result.update(field.method(attr, _serialize))  # type: ignore
            for alias, field in fields:
                attr = getattr(obj, field.name)
                if attr is not Undefined:
                    result[alias] = field.method(attr, _serialize)  # type: ignore
            for alias, method in serialized_fields:
                res = method(obj, _serialize)
                if res is not Undefined:
                    result[alias] = res
            return result
        if obj is Undefined:
            raise Unsupported(cls)
        if issubclass(cls, Enum):
            return _serialize(obj.value)
        if isinstance(obj, PRIMITIVE_TYPES):
            return obj
        if isinstance(obj, Mapping):
            return {_serialize(key): _serialize(value) for key, value in obj.items()}
        if isinstance(obj, Collection):
            return [_serialize(elt) for elt in obj]
        if issubclass(cls, tuple) and hasattr(cls, "_fields"):
            result = {}
            for field_name in obj._fields:
                attr = getattr(obj, field_name)
                if attr is not Undefined:
                    result[aliaser(field_name)] = attr
            return result
        raise Unsupported(cls)

    return _serialize(obj, conversions=conversions)


def has_parameter_without_default(resolver) -> bool:
    return any(arg.default is Parameter.empty for arg in resolver.parameters)


def can_be_serialized(resolver: Resolver) -> bool:
    return not has_parameter_without_default(resolver) and not resolver.is_async


def check_serialized(cls: Type, name: str):
    resolver = get_resolvers(cls)[name]
    if has_parameter_without_default(resolver):
        raise TypeError(f"{resolver.func} cannot have parameter without default")
    try:
        if resolver.is_async:
            raise TypeError(f"async {resolver.func} cannot be serialized")
    except Exception:  # get_type_hints can fail
        if iscoroutinefunction(resolver.func):
            raise TypeError(f"coroutine {resolver.func} cannot be serialized")


class SerializedDescriptor:
    def __init__(self, resolver_desc: ResolverDescriptor):
        self.resolver_desc = resolver_desc

    def __set_name__(self, owner, name):
        self.resolver_desc.__set_name__(owner, name)
        check_serialized(owner, self.resolver_desc.name or name)


def _serialized(*args, **kwargs):
    result = resolver(*args, **kwargs)
    if isinstance(result, ResolverDescriptor):
        return SerializedDescriptor(result)
    else:
        return lambda method: SerializedDescriptor(result(method))


serialized = typed_wraps(resolver)(_serialized)


def _add_serialized(cls, name=None, **kwargs):
    def decorator(func):
        result = add_resolver(cls, name=name, **kwargs)(func)
        check_serialized(cls, name or func.__name__)
        return result

    return decorator


add_serialized = typed_wraps(add_resolver)(_add_serialized)


def get_serialized_resolvers(cls: Type) -> Mapping[str, Resolver]:
    return {
        name: res for name, res in get_resolvers(cls).items() if can_be_serialized(res)
    }
