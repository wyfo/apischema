from collections import ChainMap, defaultdict
from dataclasses import dataclass
from functools import wraps
from inspect import Parameter, iscoroutinefunction, signature
from typing import (
    Any,
    Awaitable,
    Callable,
    Collection,
    Dict,
    Mapping,
    Optional,
    Sequence,
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
from apischema.typing import get_type_hints
from apischema.utils import get_origin_or_class

Description = Union[str, "ellipsis", None]  # noqa: F821


@dataclass
class ResolverParameter:
    name: str
    type: AnyType
    default: Any


@dataclass(frozen=True)
class Resolver:
    func: Callable
    return_type: AnyType
    parameters: Collection[ResolverParameter]
    conversions: Optional[Conversions] = None
    schema: Optional[Schema] = None

    @property
    def is_async(self) -> bool:
        return iscoroutinefunction(self.func) or issubclass(
            get_origin_or_class(self.return_type), Awaitable
        )


def resolver_types(
    resolver: Callable, cls: Type
) -> Tuple[bool, AnyType, Sequence[ResolverParameter]]:
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
                ResolverParameter(param.name, types[param.name], param.default)
            )
    if not instance_method and arguments:
        if (get_origin_or_class(arguments[0].type)) == cls:
            instance_method = True
            arguments = arguments[1:]
    return instance_method, types["return"], arguments


_resolvers: Dict[Type, Dict[str, Resolver]] = defaultdict(dict)


def get_resolvers(cls: Type) -> Mapping[str, Resolver]:
    all_resolvers = (
        _resolvers[sub_cls]
        for cls2 in (cls, get_model_origin(cls))
        for sub_cls in reversed(cls2.__mro__)
    )
    return ChainMap(*all_resolvers)


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

        elif iscoroutinefunction(self.func):

            @wraps(self.func.__get__(None, owner))
            async def method(self, *args, **kwargs):
                return await getattr(self, name)(*args, **kwargs)

        else:

            @wraps(self.func.__get__(None, owner))
            def method(self, *args, **kwargs):
                return getattr(self, name)(*args, **kwargs)

        _, return_type, parameters = resolver_types(method, owner)

        _resolvers[owner][self.name or name] = Resolver(
            method,
            return_type,
            parameters,
            self.conversions,
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
        instance_method, return_type, parameters = resolver_types(func, cls)
        if instance_method:
            method: Callable = func
        else:
            method = lambda __, *args, **kwargs: func(*args, **kwargs)  # noqa: E731
        _resolvers[cls][name or func.__name__] = Resolver(
            method, return_type, parameters, conversions, schema
        )
        return func

    return decorator
