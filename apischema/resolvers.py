from collections import defaultdict
from dataclasses import dataclass
from functools import wraps
from inspect import Parameter, signature
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
    overload,
)

from apischema.conversions import Conversions
from apischema.conversions.dataclass_model import get_model_origin
from apischema.json_schema.schema import Schema
from apischema.types import AnyType
from apischema.typing import get_origin, get_type_hints

Description = Union[str, "ellipsis", None]  # noqa: F821


@dataclass
class ResolverArgument:
    name: str
    type: AnyType
    default: Any


@dataclass(frozen=True)
class Resolver:
    func: Callable
    conversions: Optional[Conversions]
    return_type: AnyType
    arguments: Collection[ResolverArgument]
    schema: Optional[Schema]


def resolver_types(
    resolver: Callable, cls: Type
) -> Tuple[bool, AnyType, Collection[ResolverArgument]]:
    types = get_type_hints(resolver, include_extras=True)
    if "return" not in types:
        raise TypeError("Resolver must be typed")
    arguments, instance_method = [], False
    params = list(signature(resolver).parameters.values())
    if params and params[0].name == "self":
        instance_method = True
        params = params[1:]
    for param in params:
        if param.kind is Parameter.POSITIONAL_ONLY:
            raise TypeError("Resolver can not have positional only parameters")
        if param.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
            if param.name not in types:
                raise TypeError("Resolver must be typed")
            arguments.append(
                ResolverArgument(param.name, types[param.name], param.default)
            )
    if not instance_method and arguments:
        first_arg_type = arguments[0].type
        if (get_origin(first_arg_type) or first_arg_type) == cls:
            instance_method = True
            arguments = arguments[1:]
    return instance_method, types["return"], arguments


_resolvers: Dict[Type, Dict[str, Resolver]] = defaultdict(dict)


def get_resolvers(cls: Type) -> Mapping[str, Resolver]:
    return {**_resolvers[cls], **_resolvers[get_model_origin(cls)]}


class ResolverDescriptor:
    def __init__(
        self,
        func: Any,
        name: str = None,
        conversions: Conversions = None,
        schema: Schema = None,
    ):
        self.func = func
        self.name = name
        self.conversions = conversions
        self.schema = schema

    def __set_name__(self, owner, name):
        if isinstance(self.func, property):

            @wraps(self.func.fget)
            def method(self):
                return getattr(self, name)

        else:

            @wraps(self.func.__get__(None, owner))
            def method(self, *args, **kwargs):
                return getattr(self, name)(*args, **kwargs)

        _, return_type, arguments = resolver_types(method, owner)

        _resolvers[owner][self.name or name] = Resolver(
            method,
            self.conversions,
            return_type,
            arguments,
            self.schema,
        )
        setattr(owner, name, self.func)

    def __call__(self, *args, **kwargs):
        raise TypeError("Resolver method {self.__set_name__ has not been called")


MethodOrProperty = TypeVar(
    "MethodOrProperty", bound=Union[Callable, staticmethod, classmethod, property]
)


@overload
def resolver(__method_or_property: MethodOrProperty) -> MethodOrProperty:
    ...


@overload
def resolver(
    alias: str = None, *, conversions: Conversions = None, schema: Schema = None
) -> Callable[[MethodOrProperty], MethodOrProperty]:
    ...


def resolver(
    __arg=None,
    *,
    alias: str = None,
    conversions: Conversions = None,
    schema: Schema = None,
):
    if isinstance(__arg, str) or __arg is None:
        return lambda method: ResolverDescriptor(
            method, alias or __arg, conversions, schema
        )
    return ResolverDescriptor(__arg)


Func = TypeVar("Func", bound=Callable)


def add_resolver(
    cls: Type,
    name: str = None,
    *,
    conversions: Conversions = None,
    schema: Schema = None,
) -> Callable[[Func], Func]:
    def decorator(func: Func) -> Func:
        instance_method, return_type, arguments = resolver_types(func, cls)
        if instance_method:
            method: Callable = func
        else:
            method = lambda __, *args, **kwargs: func(*args, **kwargs)  # noqa: E731
        _resolvers[cls][name or func.__name__] = Resolver(
            method, conversions, return_type, arguments, schema
        )
        return func

    return decorator
