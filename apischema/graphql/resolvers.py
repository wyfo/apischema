from collections import ChainMap, defaultdict
from contextlib import suppress
from dataclasses import dataclass
from inspect import Parameter, signature
from itertools import takewhile
from typing import (
    Any,
    Awaitable,
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

from graphql import GraphQLResolveInfo

from apischema.deserialization import deserialize
from apischema.json_schema.annotations import Deprecated
from apischema.serialization import serialize
from apischema.types import AnyType
from apischema.typing import get_args, get_origin, get_type_hints
from apischema.validation.errors import ValidationError

ResolverAttribute = str
ResolverName = str

Description = Union[str, "ellipsis", None]  # noqa: F821


@dataclass(frozen=True)
class ResolverArgument:
    name: str
    type: AnyType
    default: Any


@dataclass(frozen=True)
class ResolverSchema:
    description: Description
    deprecated: Deprecated


@dataclass(frozen=True)
class Resolver:
    func: Callable
    schema: ResolverSchema

    @property
    def deprecated(self) -> Deprecated:
        return self.schema.deprecated

    @property
    def description(self) -> Optional[str]:
        if self.schema.description is not None:
            if self.schema.description is not ...:
                assert isinstance(self.schema.description, str)
                return self.schema.description
            elif self.func.__doc__:
                lines = self.func.__doc__.strip().split("\n")
                return "\n".join(takewhile(lambda l: l.strip(), lines))
        return None


_resolvers: Dict[
    Type, Dict[ResolverName, Tuple[ResolverAttribute, ResolverSchema]]
] = defaultdict(dict)
_additional_resolvers: Dict[
    Type, Dict[str, Tuple[Callable, ResolverSchema]]
] = defaultdict(dict)


def get_resolvers(cls: Type) -> Mapping[ResolverName, Resolver]:
    return {
        name: Resolver(func, schema)
        for name, (func, schema) in ChainMap(
            _additional_resolvers[cls],
            {
                name: (getattr(cls, attr), schema)
                for name, (attr, schema) in _resolvers[cls].items()
            },
        ).items()
    }


awaitable_origin = get_origin(Awaitable[Any])


class MissingFirstParam(Exception):
    pass


def resolver_types_and_wrapper(
    resolver: Callable, force_self_param: bool = False
) -> Tuple[AnyType, Collection[ResolverArgument], Callable]:
    types = get_type_hints(resolver, include_extras=True)
    if "return" not in types:
        raise TypeError("Resolver must be typed")
    ret = types["return"]
    if get_origin(ret) == awaitable_origin:
        ret = get_args(ret)[0]
    arguments, self_param, info_param = [], False, None
    params = list(signature(resolver).parameters.values())
    if force_self_param and not params:
        raise MissingFirstParam
    if params and params[0].name == "self":
        params = params[1:]
        self_param = True
    for param in params:
        if param.kind is Parameter.POSITIONAL_ONLY:
            raise TypeError("Resolver can not have positional only parameters")
        if param.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
            if param.name not in types:
                raise TypeError("Resolver must be typed")
            if types[param.name] in {GraphQLResolveInfo, Optional[GraphQLResolveInfo]}:
                info_param = param.name
            else:
                arguments.append(
                    ResolverArgument(param.name, types[param.name], param.default)
                )
    resolve: Callable
    if self_param and not arguments and info_param is None:

        def resolve(self, _):
            return resolver(self)

    else:

        def resolve(self, info, **kwargs):
            assert kwargs.keys() <= {arg.name for arg in arguments}
            errors: Dict[str, ValidationError] = {}
            kwargs2 = {}
            for arg in arguments:
                if arg.name in kwargs:
                    try:
                        kwargs2[arg.name] = deserialize(arg.type, kwargs[arg.name])
                    except ValidationError as err:
                        errors[arg.name] = err
                elif arg.default is Parameter.empty:
                    errors[arg.name] = ValidationError(["missing argument"])
            if errors:
                raise TypeError(serialize(ValidationError(children=errors)))
            if info_param:
                kwargs2[info_param] = info
            args = (self,) if self_param else ()
            return resolver(*args, **kwargs2)

    return ret, arguments, resolve


class ResolverDescriptor:
    def __init__(self, attribute: Any, name: Optional[str], schema: ResolverSchema):
        self.attribute = attribute
        self.name = name
        self.schema = schema

    def __set_name__(self, owner, name):
        _resolvers[owner][self.name or name] = name, self.schema
        with suppress(Exception):
            setattr(owner, name, self.attribute)

    def __call__(self, *args, **kwargs):
        raise TypeError("__set_name__ has not been called")


MethodOrProperty = TypeVar(
    "MethodOrProperty", bound=Union[Callable, staticmethod, classmethod, property]
)


@overload
def resolver(__method_or_property: MethodOrProperty) -> MethodOrProperty:
    ...


@overload
def resolver(
    __name: str, description: Description = ..., deprecated: Deprecated = False
) -> Callable[[MethodOrProperty], MethodOrProperty]:
    ...


def resolver(
    __arg=None, description: Description = ..., deprecated: Deprecated = False
):
    schema = ResolverSchema(description, deprecated)
    if callable(__arg):
        return ResolverDescriptor(__arg, None, schema)
    else:
        return lambda method: ResolverDescriptor(method, __arg, schema)


Func = TypeVar("Func", bound=Callable)


def add_resolver(
    cls: Type,
    name: str = None,
    description: Description = ...,
    deprecated: Deprecated = False,
) -> Callable[[Func], Func]:
    def decorator(func: Func) -> Func:
        _additional_resolvers[cls][name or func.__name__] = func, ResolverSchema(
            description, deprecated
        )
        return func

    return decorator
