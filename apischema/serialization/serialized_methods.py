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
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.conversions.conversions import Conversions
from apischema.conversions.dataclass_models import get_model_origin, has_model_origin
from apischema.json_schema.schema import Schema
from apischema.types import AnyType
from apischema.typing import generic_mro, get_args, get_type_hints
from apischema.utils import (
    MethodOrProperty,
    MethodWrapper,
    Undefined,
    UndefinedType,
    get_args2,
    get_origin2,
    get_origin_or_type,
    get_parameters,
    is_method,
    method_class,
    method_wrapper,
    substitute_type_vars,
)


@dataclass(frozen=True)
class Serialized:
    func: Callable
    conversions: Optional[Conversions]
    schema: Optional[Schema]
    error_handler: Optional[Callable]

    def error_type(self) -> AnyType:
        assert self.error_handler is not None
        types = get_type_hints(self.error_handler, include_extras=True)
        if "return" not in types:
            raise TypeError("Error handler must be typed")
        return types["return"]

    def return_type(self, return_type: AnyType) -> AnyType:
        if self.error_handler is not None:
            error_type = self.error_type()
            if error_type is not NoReturn:
                return Union[return_type, error_type]
        return return_type

    def types(self, owner: AnyType = None) -> Mapping[str, AnyType]:
        types = get_type_hints(self.func, include_extras=True)
        if "return" not in types:
            if isclass(self.func):
                types["return"] = self.func
            else:
                raise TypeError("Function must be typed")
        types["return"] = self.return_type(types["return"])
        if get_args2(owner):
            substitution = dict(
                zip(get_parameters(get_origin2(owner)), get_args2(owner))
            )
            types = {
                name: substitute_type_vars(tp, substitution)
                for name, tp in types.items()
            }
        return types


_serialized_methods: Dict[Type, Dict[str, Serialized]] = defaultdict(dict)

S = TypeVar("S", bound=Serialized)


def _get_methods(
    tp: AnyType, all_methods: Mapping[Type, Mapping[str, S]]
) -> Mapping[str, Tuple[S, Mapping[str, AnyType]]]:
    result = {}
    for base in reversed(generic_mro(tp)):
        for name, method in all_methods[get_origin_or_type(base)].items():
            result[name] = (method, method.types(base))
    if has_model_origin(tp):
        origin = get_model_origin(tp)
        if get_args2(tp):
            substitution = dict(zip(get_parameters(tp), get_args(tp)))
            origin = substitute_type_vars(origin, substitution)
        result.update(_get_methods(origin, all_methods))
    return result


def get_serialized_methods(
    tp: AnyType,
) -> Mapping[str, Tuple[Serialized, Mapping[str, AnyType]]]:
    return _get_methods(tp, _serialized_methods)


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
            owner = get_origin_or_type(get_type_hints(func)[parameters[0].name])
        except KeyError:
            raise TypeError(
                "First parameter of serialized method must be typed"
            ) from None
    _serialized_methods[owner][alias] = serialized


class SerializedDescriptor(MethodWrapper[MethodOrProperty]):
    def __init__(
        self,
        method: MethodOrProperty,
        alias: Optional[str],
        conversions: Optional[Conversions],
        schema: Optional[Schema],
        error_handler: ErrorHandler,
    ):
        super().__init__(method)
        self._alias = alias
        self._conversions = conversions
        self._schema = schema
        self._error_handler = error_handler

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        register_serialized(
            method_wrapper(self._method, name),
            self._alias or name,
            self._conversions,
            self._schema,
            self._error_handler,
            owner,
        )

    def __call__(self, *args, **kwargs):
        raise RuntimeError("Method __set_name__ has not been called")


MethodOrProp = TypeVar("MethodOrProp", Callable, property)


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
    def decorator(method: MethodOrProperty):
        nonlocal owner
        if is_method(method) and method_class(method) is None:
            return SerializedDescriptor(
                method, alias, conversions, schema, error_handler
            )
        else:
            if is_method(method):
                if owner is None:
                    owner = method_class(method)
                method = method_wrapper(method)
            assert not isinstance(method, property)
            register_serialized(
                cast(Callable, method),
                alias or method.__name__,
                conversions,
                schema,
                error_handler,
                owner,
            )
            return method

    if isinstance(__arg, str) or __arg is None:
        alias = alias or __arg
        return decorator
    else:
        return decorator(__arg)
