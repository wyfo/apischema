from collections import defaultdict
from dataclasses import dataclass
from functools import wraps
from inspect import Parameter, isclass, signature
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    NoReturn,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.conversions import Conversions
from apischema.conversions.dataclass_models import get_model_origin, has_model_origin
from apischema.json_schema.schema import Schema
from apischema.types import AnyType
from apischema.typing import get_type_hints
from apischema.utils import (
    MethodOrProperty,
    Undefined,
    UndefinedType,
    cached_property,
    get_origin_or_class,
    is_method,
    method_wrapper,
)


@dataclass(frozen=True)
class Serialized:
    func: Callable
    conversions: Optional[Conversions]
    schema: Optional[Schema]
    error_handler: Optional[Callable]

    @cached_property
    def types(self) -> Mapping[str, AnyType]:
        types = get_type_hints(self.func, include_extras=True)
        if "return" not in types:
            if isclass(self.func):
                types["return"] = self.func
            else:
                raise TypeError("Function must be typed")
        return types

    @cached_property
    def error_handler_types(self) -> Mapping[str, AnyType]:
        assert self.error_handler is not None
        types = get_type_hints(self.error_handler, include_extras=True)
        if "return" not in types:
            raise TypeError("Error handler must be typed")
        return types

    @property
    def return_type(self) -> AnyType:
        ret = self.types["return"]
        if self.error_handler is not None:
            error_ret = self.error_handler_types["return"]
            if error_ret is not NoReturn:
                return Union[ret, error_ret]
        return ret


_serialized_methods: Dict[Type, Dict[str, Serialized]] = defaultdict(dict)


def get_serialized_methods(cls: Type) -> Mapping[str, Serialized]:
    serialized = {}
    for sub_cls in cls.__mro__:
        serialized.update(_serialized_methods[sub_cls])
    if has_model_origin(cls):
        serialized.update(get_serialized_methods(get_model_origin(cls)))
    return serialized


ErrorHandler = Union[Callable, None, UndefinedType]


def none_error_handler(error: Exception, obj: Any, alias: str) -> None:
    return None


def register_serialized(
    func: Callable,
    alias: str,
    conversions: Optional[Conversions],
    schema: Optional[Schema],
    error_handler: ErrorHandler,
    owner: Type = None,
):
    parameters = list(signature(func).parameters.values())
    for param in parameters[1:]:
        if (
            param.kind not in {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}
            and param.default is Parameter.empty
        ):
            raise TypeError("Serialized method cannot have parameter without default")
    if error_handler is None:
        error_handler = none_error_handler
    if error_handler is Undefined:
        error_handler = None
    else:
        wrapped = func

        @wraps(wrapped)
        def func(self):
            try:
                return wrapped(self)
            except Exception as error:
                return error_handler(error, self, alias)

    assert not isinstance(error_handler, UndefinedType)
    serialized = Serialized(func, conversions, schema, error_handler)
    if owner is None:
        try:
            owner = get_origin_or_class(serialized.types[parameters[0].name])
        except KeyError:
            raise TypeError(
                "First parameter of serialized method must be typed"
            ) from None
    _serialized_methods[owner][alias] = serialized


class SerializedDescriptor:
    def __init__(
        self,
        func: MethodOrProperty,
        alias: Optional[str],
        conversions: Optional[Conversions],
        schema: Optional[Schema],
        error_handler: ErrorHandler,
    ):
        self.func = func
        self.alias = alias
        self.conversions = conversions
        self.schema = schema
        self.error_handler = error_handler

    def __set_name__(self, owner, name):
        register_serialized(
            method_wrapper(self.func, name),
            self.alias or name,
            self.conversions,
            self.schema,
            self.error_handler,
            owner,
        )
        setattr(owner, name, self.func)

    def __call__(self, *args, **kwargs):
        raise RuntimeError("Method __set_name__ has not been called")


MethodOrProp = TypeVar("MethodOrProp", bound=MethodOrProperty)


@overload
def serialized(__method_or_property: MethodOrProp) -> MethodOrProp:
    ...


@overload
def serialized(
    alias: str = None,
    *,
    conversions: Conversions = None,
    schema: Schema = None,
    error_handler: ErrorHandler = Undefined,
    owner: Type = None,
) -> Callable[[MethodOrProp], MethodOrProp]:
    ...


def serialized(
    __arg=None,
    *,
    alias: str = None,
    conversions: Conversions = None,
    schema: Schema = None,
    error_handler: ErrorHandler = Undefined,
    owner: Type = None,
):
    def decorator(func: MethodOrProp) -> MethodOrProp:
        if isinstance(func, (classmethod, staticmethod)):
            raise TypeError("Serialized method cannot be staticmethod/classmethod")
        if is_method(func):
            return cast(
                MethodOrProp,
                SerializedDescriptor(func, alias, conversions, schema, error_handler),
            )
        else:
            register_serialized(
                cast(Callable, func),
                alias or func.__name__,
                conversions,
                schema,
                error_handler,
                owner,
            )
            return func

    if isinstance(__arg, str) or __arg is None:
        alias = alias or __arg
        return decorator
    else:
        return decorator(__arg)
