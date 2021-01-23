from collections import defaultdict
from dataclasses import dataclass, is_dataclass
from enum import Enum
from inspect import Parameter, iscoroutinefunction, signature
from typing import (
    Any,
    Awaitable,
    Callable,
    Collection,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    cast,
    overload,
)

import graphql

from apischema.aliases import Aliaser
from apischema.conversions.conversions import Conversions, to_hashable_conversions
from apischema.conversions.dataclass_models import DataclassModel
from apischema.deserialization import deserialize
from apischema.json_schema.schema import Schema
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
    SerializedDescriptor,
    _get_methods,
    register_serialized,
)
from apischema.types import AnyType, NoneType, PRIMITIVE_TYPES
from apischema.typing import get_origin, get_type_hints
from apischema.utils import (
    MethodOrProperty,
    Undefined,
    UndefinedType,
    get_args2,
    get_origin_or_type,
    is_method,
    is_union_of,
    method_class,
    method_wrapper,
)
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
    conversion = get_conversions(cls, to_hashable_conversions(conversions))
    if conversion is not None:
        if isinstance(conversion.target, DataclassModel):
            return obj
        return partial_serialize(
            conversion.converter(obj),  # type: ignore
            conversions=conversion.conversions,
            aliaser=aliaser,
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

    def error_type(self) -> AnyType:
        return unwrap_awaitable(super().error_type())

    def return_type(self, return_type: AnyType) -> AnyType:
        return super().return_type(unwrap_awaitable(return_type))

    def types(self, owner: AnyType = None) -> Mapping[str, AnyType]:
        types = super().types(owner)
        if is_union_of(types["return"], UndefinedType):
            raise TypeError("Resolver cannot return Undefined")
        return types


_resolvers: Dict[Type, Dict[str, Resolver]] = defaultdict(dict)


def get_resolvers(tp: AnyType) -> Mapping[str, Tuple[Resolver, Mapping[str, AnyType]]]:
    return _get_methods(tp, _resolvers)


def none_error_handler(
    __error: Exception, __obj: Any, __info: graphql.GraphQLResolveInfo, **kwargs
) -> None:
    return None


def resolver_parameters(
    resolver: Callable, *, check_first: bool
) -> Iterable[Parameter]:
    first = True
    for param in signature(resolver).parameters.values():
        if param.kind is Parameter.POSITIONAL_ONLY:
            raise TypeError("Resolver can not have positional only parameters")
        if param.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
            if param.annotation is Parameter.empty and (check_first or not first):
                raise TypeError("Resolver parameters must be typed")
            yield param
        first = False


def register_resolver(
    func: Callable,
    alias: str,
    conversions: Optional[Conversions],
    schema: Optional[Schema],
    error_handler: ErrorHandler,
    serialized: bool,
    owner: Type = None,
):
    first_param, *parameters = resolver_parameters(func, check_first=owner is None)
    if error_handler is None:
        error_handler = none_error_handler
    elif error_handler is Undefined:
        error_handler = None
    resolver = Resolver(func, conversions, schema, error_handler, parameters)
    if owner is None:
        try:
            owner = get_origin_or_type(get_type_hints(func)[first_param.name])
        except KeyError:
            raise TypeError("First parameter of resolver must be typed") from None
    _resolvers[owner][alias] = resolver
    if serialized:
        if is_async(func):
            raise TypeError("Async resolver cannot be used as a serialized method")
        try:
            register_serialized(func, alias, conversions, schema, error_handler, owner)
        except Exception:
            raise TypeError("Resolver cannot be used as a serialized method")


class ResolverDescriptor(SerializedDescriptor):
    def __init__(
        self,
        method: MethodOrProperty,
        alias: Optional[str],
        conversions: Optional[Conversions],
        schema: Optional[Schema],
        error_handler: ErrorHandler,
        serialized: bool,
    ):
        super().__init__(method, alias, conversions, schema, error_handler)
        self.serialized = serialized

    def __set_name__(self, owner, name):
        register_resolver(
            method_wrapper(self._method),
            self._alias or name,
            self._conversions,
            self._schema,
            self._error_handler,
            self.serialized,
            owner,
        )
        setattr(owner, name, self._method)


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
    serialized: bool = False,
    owner: Type = None,
):
    def decorator(method: MethodOrProperty):
        nonlocal owner
        if is_method(method) and method_class(method) is None:
            return ResolverDescriptor(
                method, alias, conversions, schema, error_handler, serialized
            )
        else:
            if is_method(method):
                if owner is None:
                    owner = method_class(method)
                method = method_wrapper(method)
            assert not isinstance(method, property)
            register_resolver(
                cast(Callable, method),
                alias or method.__name__,
                conversions,
                schema,
                error_handler,
                serialized,
                owner,
            )
            return method

    if isinstance(__arg, str) or __arg is None:
        alias = alias or __arg
        return decorator
    else:
        return decorator(__arg)


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
            parameters.append(
                (
                    aliaser(param.name),
                    param.name,
                    param_type,
                    is_union_of(param_type, NoneType),
                    param.default is Parameter.empty,
                )
            )
    func, error_handler = resolver.func, resolver.error_handler

    def no_serialize(result):
        return result

    async def async_serialize(result: Awaitable):
        return partial_serialize(
            await result, conversions=resolver.conversions, aliaser=aliaser
        )

    def sync_serialize(result):
        return partial_serialize(
            result, conversions=resolver.conversions, aliaser=aliaser
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
        for alias, param_name, param_type, opt_param, is_required in parameters:
            if param_name in kwargs:
                if not opt_param and kwargs[param_name] is None:
                    assert not is_required
                    continue
                try:
                    values[param_name] = deserialize(
                        param_type, kwargs[param_name], aliaser=aliaser
                    )
                except ValidationError as err:
                    errors[aliaser(param_name)] = err
            elif opt_param and is_required:
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
