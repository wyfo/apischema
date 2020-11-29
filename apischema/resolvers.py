__all__ = ["add_resolver", "resolver"]
from collections import ChainMap, defaultdict
from dataclasses import dataclass
from inspect import Parameter, iscoroutinefunction, signature
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    overload,
)

from apischema.conversions import Conversions
from apischema.conversions.dataclass_model import get_model_origin
from apischema.json_schema.schema import Schema
from apischema.types import AnyType
from apischema.typing import get_args, get_origin, get_type_hints
from apischema.utils import cached_property, get_origin_or_class

Description = Union[str, "ellipsis", None]  # noqa: F821

awaitable_origin = get_origin(Awaitable[Any])


@dataclass(frozen=True)
class Resolver:
    func: Callable
    wrapper: Callable
    parameters: Sequence[Parameter]
    conversions: Optional[Conversions] = None
    schema: Optional[Schema] = None

    @cached_property
    def types(self) -> Mapping[str, AnyType]:
        return get_type_hints(self.func, include_extras=True)

    @property
    def return_type(self) -> AnyType:
        ret = self.types["return"]
        return get_args(ret)[0] if get_origin(ret) == awaitable_origin else ret

    @property
    def is_async(self) -> bool:
        if iscoroutinefunction(self.func):
            return True
        try:
            return issubclass(get_origin_or_class(self.types["return"]), Awaitable)
        except Exception:  # py36 has weird AttributeError with issubclass
            return False


class MissingFirstParameter(Exception):
    pass


def resolver_parameters(resolver: Callable, *, skip_first: bool) -> Sequence[Parameter]:
    if "return" not in resolver.__annotations__:
        raise TypeError("Resolver must be typed")
    parameters = []
    params = list(signature(resolver).parameters.values())
    if skip_first:
        if not params:
            raise MissingFirstParameter
        params = params[1:]
    for param in params:
        if param.kind is Parameter.POSITIONAL_ONLY:
            raise TypeError("Resolver can not have positional only parameters")
        if param.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
            if param.annotation is Parameter.empty:
                raise TypeError("Resolver must be typed")
            parameters.append(param)
    return parameters


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
        wrapper: Callable
        if isinstance(self.func, property):
            method = self.func.fget

            def wrapper(self):
                return getattr(self, name)

        else:
            method = self.func.__get__(None, owner)

            def wrapper(self, *args, **kwargs):
                return getattr(self, name)(*args, **kwargs)

        parameters = resolver_parameters(
            method, skip_first=not isinstance(self.func, staticmethod)
        )

        _resolvers[owner][self.name or name] = Resolver(
            method,
            wrapper,
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
        parameters = resolver_parameters(func, skip_first=False)
        types = get_type_hints(func)
        if get_origin_or_class(types[parameters[0].name]) == cls:
            parameters = parameters[1:]
            wrapper: Callable = func
        else:
            wrapper = lambda __, *args, **kwargs: func(*args, **kwargs)  # noqa: E731
        _resolvers[cls][name or func.__name__] = Resolver(
            func, wrapper, parameters, conversions, schema
        )
        return func

    return decorator
