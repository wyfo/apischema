from collections import defaultdict
from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import partial
from inspect import Parameter, iscoroutinefunction, signature
from typing import (
    Any,
    Awaitable,
    Callable,
    Collection,
    Dict,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    overload,
)

import graphql

from apischema.aliases import Aliaser
from apischema.conversions.conversions import Conversions, handle_container_conversions
from apischema.conversions.dataclass_models import DataclassModel
from apischema.deserialization import deserialize
from apischema.json_schema.schema import Schema
from apischema.metadata.implem import ConversionMetadata
from apischema.metadata.keys import (
    ALIAS_METADATA,
    CONVERSIONS_METADATA,
    DEFAULT_FALLBACK_METADATA,
    REQUIRED_METADATA,
    get_annotated_metadata,
)
from apischema.serialization import (
    COLLECTION_TYPE_SET,
    MAPPING_TYPE_SET,
    PRIMITIVE_TYPES_SET,
    get_conversions,
    serialize,
)
from apischema.serialization.serialized_methods import (
    ErrorHandler,
    Serialized,
    _get_methods,
    serialized as register_serialized,
)
from apischema.types import AnyType, NoneType, PRIMITIVE_TYPES
from apischema.typing import get_origin, get_type_hints
from apischema.utils import (
    Undefined,
    get_args2,
    get_origin_or_type,
    is_union_of,
    method_registerer,
)
from apischema.validation.errors import ValidationError
from apischema.visitor import Unsupported


def partial_serialize(
    obj: Any, *, aliaser: Aliaser, conversions: Conversions = None
) -> Any:
    if obj is Undefined:
        return None
    cls = obj.__class__
    if cls in PRIMITIVE_TYPES_SET:
        return obj
    if cls in COLLECTION_TYPE_SET:
        return [
            partial_serialize(elt, aliaser=aliaser, conversions=conversions)
            for elt in obj
        ]
    if cls in MAPPING_TYPE_SET:
        return serialize(
            obj, conversions=conversions, aliaser=aliaser, exclude_unset=False
        )
    conversion, dynamic = get_conversions(cls, conversions)
    if conversion is not None:
        if isinstance(conversion.target, DataclassModel):
            return obj
        return partial_serialize(
            conversion.converter(obj),  # type: ignore
            aliaser=aliaser,
            conversions=handle_container_conversions(
                conversion.target,
                conversion.sub_conversions,
                conversions,
                dynamic,
            ),
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


awaitable_origin = get_origin(Awaitable[Any])


def is_async(func: Callable) -> bool:
    return (
        iscoroutinefunction(func)
        or get_origin_or_type(get_type_hints(func).get("return")) == awaitable_origin
    )


def unwrap_awaitable(tp: AnyType) -> AnyType:
    return get_args2(tp)[0] if get_origin_or_type(tp) == awaitable_origin else tp


@dataclass(frozen=True)
class Resolver(Serialized):
    parameters: Sequence[Parameter]
    parameters_metadata: Mapping[str, Mapping]

    def error_type(self) -> AnyType:
        return unwrap_awaitable(super().error_type())

    def return_type(self, return_type: AnyType) -> AnyType:
        return super().return_type(unwrap_awaitable(return_type))


_resolvers: Dict[Type, Dict[str, Resolver]] = defaultdict(dict)


def get_resolvers(tp: AnyType) -> Mapping[str, Tuple[Resolver, Mapping[str, AnyType]]]:
    return _get_methods(tp, _resolvers)


def none_error_handler(
    __error: Exception, __obj: Any, __info: graphql.GraphQLResolveInfo, **kwargs
) -> None:
    return None


def resolver_parameters(
    resolver: Callable, *, check_first: bool
) -> Iterator[Parameter]:
    first = True
    for param in signature(resolver).parameters.values():
        if param.kind is Parameter.POSITIONAL_ONLY:
            raise TypeError("Resolver can not have positional only parameters")
        if param.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
            if param.annotation is Parameter.empty and (check_first or not first):
                raise TypeError("Resolver parameters must be typed")
            yield param
        first = False


MethodOrProp = TypeVar("MethodOrProp", Callable, property)


@overload
def resolver(__method_or_property: MethodOrProp) -> MethodOrProp:
    ...


@overload
def resolver(
    alias: str = None,
    *,
    conversions: Conversions = None,
    schema: Schema = None,
    error_handler: ErrorHandler = Undefined,
    parameters_metadata: Mapping[str, Mapping] = None,
    serialized: bool = False,
    owner: Type = None,
) -> Callable[[MethodOrProp], MethodOrProp]:
    ...


def resolver(
    __arg=None,
    *,
    alias: str = None,
    conversions: Conversions = None,
    schema: Schema = None,
    error_handler: ErrorHandler = Undefined,
    parameters_metadata: Mapping[str, Mapping] = None,
    serialized: bool = False,
    owner: Type = None,
):
    def register(func: Callable, owner: Optional[Type], alias2: str):
        alias2 = alias or alias2
        first_param, *parameters = resolver_parameters(func, check_first=owner is None)
        error_handler2 = error_handler
        if error_handler2 is None:
            error_handler2 = none_error_handler
        elif error_handler2 is Undefined:
            error_handler2 = None
        resolver = Resolver(
            func,
            conversions,
            schema,
            error_handler2,
            parameters,
            parameters_metadata or {},
        )
        if owner is None:
            try:
                owner = get_origin_or_type(get_type_hints(func)[first_param.name])
            except KeyError:
                raise TypeError("First parameter of resolver must be typed") from None
        _resolvers[owner][alias2] = resolver
        if serialized:
            if is_async(func):
                raise TypeError("Async resolver cannot be used as a serialized method")
            try:
                register_serialized(
                    alias=alias2,
                    conversions=conversions,
                    schema=schema,
                    error_handler=error_handler,
                    owner=owner,
                )(func)
            except Exception:
                raise TypeError("Resolver cannot be used as a serialized method")

    if isinstance(__arg, str):
        alias = __arg
        __arg = None
    return method_registerer(__arg, owner, register)


def resolver_resolve(
    resolver: Resolver,
    types: Mapping[str, AnyType],
    aliaser: Aliaser,
    serialized: bool = True,
) -> Callable:
    parameters, info_parameter = [], None
    for param in resolver.parameters:
        param_type = types[param.name]
        if is_union_of(param_type, graphql.GraphQLResolveInfo):
            info_parameter = param.name
        else:
            metadata = get_annotated_metadata(param_type)
            if param.name in resolver.parameters_metadata:
                metadata = {**metadata, **resolver.parameters_metadata[param.name]}
            alias = metadata.get(ALIAS_METADATA, param.name)
            deserializer = partial(
                deserialize,
                param_type,
                conversions=metadata.get(
                    CONVERSIONS_METADATA, ConversionMetadata()
                ).deserialization,
                aliaser=aliaser,
                default_fallback=DEFAULT_FALLBACK_METADATA in metadata or None,
            )
            required = REQUIRED_METADATA in metadata or param.default is Parameter.empty
            opt_param = is_union_of(param_type, NoneType)
            parameters.append(
                (aliaser(alias), param.name, deserializer, opt_param, required)
            )
    func, error_handler = resolver.func, resolver.error_handler

    def no_serialize(result):
        return result

    async def async_serialize(result: Awaitable):
        return partial_serialize(
            await result, aliaser=aliaser, conversions=resolver.conversions
        )

    def sync_serialize(result):
        return partial_serialize(
            result, aliaser=aliaser, conversions=resolver.conversions
        )

    serialize_result: Callable[[Any], Any]
    if not serialized:
        serialize_result = no_serialize
    elif is_async(resolver.func):
        serialize_result = async_serialize
    else:
        serialize_result = sync_serialize
    serialize_error: Optional[Callable[[Any], Any]]
    if error_handler is None:
        serialize_error = None
    elif is_async(error_handler):
        serialize_error = async_serialize
    else:
        serialize_error = sync_serialize

    def resolve(__self, __info, **kwargs):
        values = {}
        errors: Dict[str, ValidationError] = {}
        for alias, param_name, deserializer, opt_param, required in parameters:
            if alias in kwargs:
                if not opt_param and kwargs[param_name] is None:
                    assert not required
                    continue
                try:
                    values[param_name] = deserializer(kwargs[alias])
                except ValidationError as err:
                    errors[aliaser(param_name)] = err
            elif opt_param and required:
                values[param_name] = None

        if errors:
            raise TypeError(serialize(ValidationError(children=errors)))
        if info_parameter:
            values[info_parameter] = __info
        try:
            return serialize_result(func(__self, **values))
        except Exception as error:
            if error_handler is None:
                raise
            assert serialize_error is not None
            return serialize_error(error_handler(error, __self, __info, **kwargs))

    return resolve
