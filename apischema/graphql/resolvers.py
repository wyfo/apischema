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
    NoReturn,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

import graphql

from apischema.aliases import Aliaser
from apischema.conversions import Conversions
from apischema.conversions.dataclass_models import (
    DataclassModelWrapper,
    get_model_origin,
    has_model_origin,
)
from apischema.conversions.visitor import SerializationVisitor
from apischema.deserialization import deserialize
from apischema.json_schema.schema import Schema
from apischema.serialization import (
    COLLECTION_TYPE_SET,
    MAPPING_TYPE_SET,
    PRIMITIVE_TYPES_SET,
    serialize,
)
from apischema.serialization.serialized_methods import (
    ErrorHandler,
    Serialized,
    SerializedDescriptor,
    register_serialized,
)
from apischema.types import AnyType, NoneType, PRIMITIVE_TYPES
from apischema.typing import get_args, get_origin, get_type_hints
from apischema.utils import (
    MethodOrProperty,
    Undefined,
    UndefinedType,
    get_origin_or_class,
    is_method,
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


awaitable_origin = get_origin(Awaitable[Any])


def is_async(func: Callable) -> bool:
    return (
        iscoroutinefunction(func)
        or get_origin_or_class(get_type_hints(func).get("return")) == awaitable_origin
    )


def unwrap_awaitable(tp: AnyType) -> AnyType:
    return get_args(tp)[0] if get_origin_or_class(tp) == awaitable_origin else tp


@dataclass(frozen=True)
class Resolver(Serialized):
    parameters: Sequence[Parameter]

    @property
    def return_type(self) -> AnyType:
        ret = unwrap_awaitable(self.types["return"])
        if self.error_handler is not None:
            error_ret = unwrap_awaitable(self.error_handler_types["return"])
            if error_ret is not NoReturn:
                ret = Union[ret, error_ret]
        if get_origin(ret) == Union and UndefinedType in get_args(ret):
            raise TypeError("Resolver cannot return Undefined")
        return ret


_resolvers: Dict[Type, Dict[str, Resolver]] = defaultdict(dict)


def get_resolvers(cls: Type) -> Mapping[str, Resolver]:
    resolvers = {}
    for sub_cls in cls.__mro__:
        resolvers.update(_resolvers[sub_cls])
    if has_model_origin(cls):
        resolvers.update(get_resolvers(get_model_origin(cls)))
    return resolvers


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
            owner = get_origin_or_class(resolver.types[first_param.name])
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
        func: MethodOrProperty,
        alias: Optional[str],
        conversions: Optional[Conversions],
        schema: Optional[Schema],
        error_handler: ErrorHandler,
        serialized: bool,
    ):
        super().__init__(func, alias, conversions, schema, error_handler)
        self.serialized = serialized

    def __set_name__(self, owner, name):
        register_resolver(
            method_wrapper(self.func, name),
            self.alias or name,
            self.conversions,
            self.schema,
            self.error_handler,
            self.serialized,
            owner,
        )
        setattr(owner, name, self.func)


MethodOrProp = TypeVar("MethodOrProp", bound=MethodOrProperty)


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
    def decorator(func: MethodOrProp) -> MethodOrProp:
        if is_method(func):
            return cast(
                MethodOrProp,
                ResolverDescriptor(
                    func, alias, conversions, schema, error_handler, serialized
                ),
            )
        else:
            register_resolver(
                cast(Callable, func),
                alias or func.__name__,
                conversions,
                schema,
                error_handler,
                serialized,
                owner,
            )
            return func

    if isinstance(__arg, str) or __arg is None:
        alias = alias or __arg
        return decorator
    else:
        return decorator(__arg)


def resolver_resolve(
    resolver: Resolver, aliaser: Aliaser, serialized: bool = True
) -> Callable:
    parameters, info_parameter = [], None
    for param in resolver.parameters:
        param_type = resolver.types[param.name]
        is_union = get_origin(param_type) == Union
        if param_type == graphql.GraphQLResolveInfo or (
            is_union and graphql.GraphQLResolveInfo in get_args(param_type)
        ):
            info_parameter = param.name
        else:
            parameters.append(
                (param.name, param_type, is_union and NoneType in get_args(param_type))
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
        errors: Dict[str, ValidationError] = {}
        for param_name, param_type, opt_param in parameters:
            if param_name in kwargs:
                if not opt_param and kwargs[param_name] is None:
                    kwargs.pop(param_name)
                    continue
                try:
                    kwargs[param_name] = deserialize(param_type, kwargs[param_name])
                except ValidationError as err:
                    errors[aliaser(param_name)] = err
        if errors:
            raise TypeError(serialize(ValidationError(children=errors)))
        if info_parameter:
            kwargs[info_parameter] = __info
        try:
            return serialize_result(func(__self, **kwargs))
        except Exception as error:
            if error_handler is None:
                raise
            assert serialize_error is not None
            return serialize_error(error_handler(error, __self, __info, **kwargs))

    return resolve
