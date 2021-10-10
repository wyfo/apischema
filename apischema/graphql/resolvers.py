from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from inspect import Parameter, signature
from typing import (
    Any,
    Awaitable,
    Callable,
    Collection,
    Dict,
    Iterator,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    overload,
)

import graphql

from apischema import UndefinedType
from apischema.aliases import Aliaser
from apischema.cache import CacheAwareDict, cache
from apischema.conversions import Conversion
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.deserialization import deserialization_method
from apischema.methods import method_registerer
from apischema.objects import ObjectField
from apischema.ordering import Ordering
from apischema.schemas import Schema
from apischema.serialization import (
    PassThroughOptions,
    SerializationMethod,
    SerializationMethodVisitor,
)
from apischema.serialization.serialized_methods import (
    ErrorHandler,
    SerializedMethod,
    _get_methods,
    serialized as register_serialized,
)
from apischema.types import AnyType, NoneType, Undefined
from apischema.typing import is_type
from apischema.utils import (
    awaitable_origin,
    deprecate_kwargs,
    empty_dict,
    get_args2,
    get_origin_or_type2,
    identity,
    is_async,
    is_union_of,
    keep_annotations,
)
from apischema.validation.errors import ValidationError


class PartialSerializationMethodVisitor(SerializationMethodVisitor):
    use_cache = False

    @property
    def _factory(self) -> Callable[[type], SerializationMethod]:
        return lambda _: identity

    def enum(self, cls: Type[Enum]) -> SerializationMethod:
        return identity

    def object(self, tp: AnyType, fields: Sequence[ObjectField]) -> SerializationMethod:
        return identity

    def visit(self, tp: AnyType) -> SerializationMethod:
        if tp is UndefinedType:
            return lambda obj: None
        return super().visit(tp)


@cache
def partial_serialization_method_factory(
    aliaser: Aliaser,
    conversion: Optional[AnyConversion],
    default_conversion: DefaultConversion,
) -> Callable[[AnyType], SerializationMethod]:
    @lru_cache()
    def factory(tp: AnyType) -> SerializationMethod:
        return PartialSerializationMethodVisitor(
            additional_properties=False,
            aliaser=aliaser,
            check_type=False,
            default_conversion=default_conversion,
            exclude_defaults=False,
            exclude_none=False,
            exclude_unset=False,
            fall_back_on_any=False,
            pass_through_options=PassThroughOptions(),
        ).visit_with_conv(tp, conversion)

    return factory


def unwrap_awaitable(tp: AnyType) -> AnyType:
    if get_origin_or_type2(tp) == awaitable_origin:
        return keep_annotations(get_args2(tp)[0] if get_args2(tp) else Any, tp)
    else:
        return tp


@dataclass(frozen=True)
class Resolver(SerializedMethod):
    parameters: Sequence[Parameter]
    parameters_metadata: Mapping[str, Mapping]

    def error_type(self) -> AnyType:
        return unwrap_awaitable(super().error_type())

    def return_type(self, return_type: AnyType) -> AnyType:
        return super().return_type(unwrap_awaitable(return_type))


_resolvers: MutableMapping[Type, Dict[str, Resolver]] = CacheAwareDict(
    defaultdict(dict)
)


def get_resolvers(tp: AnyType) -> Collection[Tuple[Resolver, Mapping[str, AnyType]]]:
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
    conversion: AnyConversion = None,
    error_handler: ErrorHandler = Undefined,
    order: Optional[Ordering] = None,
    schema: Schema = None,
    parameters_metadata: Mapping[str, Mapping] = None,
    serialized: bool = False,
    owner: Type = None,
) -> Callable[[MethodOrProp], MethodOrProp]:
    ...


@deprecate_kwargs({"conversions": "conversion"})
def resolver(
    __arg=None,
    *,
    alias: str = None,
    conversion: AnyConversion = None,
    error_handler: ErrorHandler = Undefined,
    order: Optional[Ordering] = None,
    schema: Schema = None,
    parameters_metadata: Mapping[str, Mapping] = None,
    serialized: bool = False,
    owner: Type = None,
):
    def register(func: Callable, owner: Type, alias2: str):
        alias2 = alias or alias2
        _, *parameters = resolver_parameters(func, check_first=owner is None)
        error_handler2 = error_handler
        if error_handler2 is None:
            error_handler2 = none_error_handler
        elif error_handler2 is Undefined:
            error_handler2 = None
        resolver = Resolver(
            func,
            alias2,
            conversion,
            error_handler2,
            order,
            schema,
            parameters,
            parameters_metadata or {},
        )
        _resolvers[owner][alias2] = resolver
        if serialized:
            if is_async(func):
                raise TypeError("Async resolver cannot be used as a serialized method")
            try:
                register_serialized(
                    alias=alias2,
                    conversion=conversion,
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


T = TypeVar("T")
U = TypeVar("U")


def as_async(func: Callable[[T], U]) -> Callable[[Awaitable[T]], Awaitable[U]]:
    async def wrapper(arg: Awaitable[T]) -> U:
        return func(await arg)

    return wrapper


def resolver_resolve(
    resolver: Resolver,
    types: Mapping[str, AnyType],
    aliaser: Aliaser,
    default_deserialization: DefaultConversion,
    default_serialization: DefaultConversion,
    serialized: bool = True,
) -> Callable:
    # graphql deserialization will give Enum objects instead of strings
    def handle_enum(tp: AnyType) -> Optional[AnyConversion]:
        if is_type(tp) and issubclass(tp, Enum):
            return Conversion(identity, source=Any, target=tp)
        return default_deserialization(tp)

    parameters, info_parameter = [], None
    for param in resolver.parameters:
        param_type = types[param.name]
        if is_union_of(param_type, graphql.GraphQLResolveInfo):
            info_parameter = param.name
        else:
            param_field = ObjectField(
                param.name,
                param_type,
                param.default is Parameter.empty,
                resolver.parameters_metadata.get(param.name, empty_dict),
                param.default,
            )
            deserializer = deserialization_method(
                param_type,
                additional_properties=False,
                aliaser=aliaser,
                coerce=False,
                conversion=param_field.deserialization,
                default_conversion=handle_enum,
                fall_back_on_default=False,
                schema=param_field.schema,
            )
            opt_param = is_union_of(param_type, NoneType) or param.default is None
            parameters.append(
                (
                    aliaser(param_field.alias),
                    param.name,
                    deserializer,
                    opt_param,
                    param_field.required,
                )
            )
    func, error_handler = resolver.func, resolver.error_handler
    method_factory = partial_serialization_method_factory(
        aliaser, resolver.conversion, default_serialization
    )

    serialize_result: Callable[[Any], Any]
    if not serialized:
        serialize_result = identity
    elif is_async(resolver.func):
        serialize_result = as_async(method_factory(types["return"]))
    else:
        serialize_result = method_factory(types["return"])
    serialize_error: Optional[Callable[[Any], Any]]
    if error_handler is None:
        serialize_error = None
    elif is_async(error_handler):
        serialize_error = as_async(method_factory(resolver.error_type()))
    else:
        serialize_error = method_factory(resolver.error_type())

    def resolve(__self, __info, **kwargs):
        values = {}
        errors: Dict[str, ValidationError] = {}
        for alias, param_name, deserializer, opt_param, required in parameters:
            if alias in kwargs:
                # It is possible for the parameter to be non-optional in Python
                # type hints but optional in the generated schema. In this case
                # we should ignore it.
                # See: https://github.com/wyfo/apischema/pull/130#issuecomment-845497392
                if not opt_param and kwargs[alias] is None:
                    assert not required
                    continue
                try:
                    values[param_name] = deserializer(kwargs[alias])
                except ValidationError as err:
                    errors[aliaser(param_name)] = err
            elif opt_param and required:
                values[param_name] = None

        if errors:
            raise ValueError(ValidationError(children=errors).errors)
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
