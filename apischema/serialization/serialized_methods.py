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
    overload,
)

from apischema.conversions.conversions import AnyConversion
from apischema.conversions.dataclass_models import get_model_origin, has_model_origin
from apischema.schemas import Schema
from apischema.types import AnyType, Undefined, UndefinedType
from apischema.typing import generic_mro, get_args, get_origin, get_type_hints
from apischema.utils import (
    deprecate_kwargs,
    get_args2,
    get_origin_or_type,
    get_origin_or_type2,
    get_parameters,
    method_registerer,
    substitute_type_vars,
    subtyping_substitution,
    type_dict_wrapper,
)


@dataclass(frozen=True)
class SerializedMethod:
    func: Callable
    conversion: Optional[AnyConversion]
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
            first_param = next(iter(signature(self.func).parameters))
            substitution, _ = subtyping_substitution(
                types.get(first_param, get_origin_or_type2(owner)), owner
            )
            types = {
                name: substitute_type_vars(tp, substitution)
                for name, tp in types.items()
            }
        return types


_serialized_methods: Dict[Type, Dict[str, SerializedMethod]] = type_dict_wrapper(
    defaultdict(dict)
)

S = TypeVar("S", bound=SerializedMethod)


def _get_methods(
    tp: AnyType, all_methods: Mapping[Type, Mapping[str, S]]
) -> Mapping[str, Tuple[S, Mapping[str, AnyType]]]:
    result = {}
    for base in reversed(generic_mro(tp)):
        for name, method in all_methods[get_origin_or_type(base)].items():
            result[name] = (method, method.types(base))
    if has_model_origin(tp):
        origin = get_model_origin(tp)
        if get_args(tp):
            substitution = dict(zip(get_parameters(get_origin(tp)), get_args(tp)))
            origin = substitute_type_vars(origin, substitution)
        result.update(_get_methods(origin, all_methods))
    return result


def get_serialized_methods(
    tp: AnyType,
) -> Mapping[str, Tuple[SerializedMethod, Mapping[str, AnyType]]]:
    return _get_methods(tp, _serialized_methods)


ErrorHandler = Union[Callable, None, UndefinedType]


def none_error_handler(error: Exception, obj: Any, alias: str) -> None:
    return None


MethodOrProp = TypeVar("MethodOrProp", Callable, property)


@overload
def serialized(__method_or_property: MethodOrProp) -> MethodOrProp:
    ...


@overload
def serialized(
    alias: str = None,
    *,
    conversion: AnyConversion = None,
    schema: Schema = None,
    error_handler: ErrorHandler = Undefined,
    owner: Type = None,
) -> Callable[[MethodOrProp], MethodOrProp]:
    ...


@deprecate_kwargs({"conversions": "conversion"})
def serialized(
    __arg=None,
    *,
    alias: str = None,
    conversion: AnyConversion = None,
    schema: Schema = None,
    error_handler: ErrorHandler = Undefined,
    owner: Type = None,
):
    def register(func: Callable, owner: Type, alias2: str):
        alias2 = alias or alias2
        parameters = list(signature(func).parameters.values())
        for param in parameters[1:]:
            if (
                param.kind not in {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}
                and param.default is Parameter.empty
            ):
                raise TypeError("Serialized method cannot have required parameter")
        error_handler2 = error_handler
        if error_handler is None:
            error_handler2 = none_error_handler
        if error_handler2 is Undefined:
            error_handler2 = None
        else:
            wrapped = func

            @wraps(wrapped)
            def func(self):
                try:
                    return wrapped(self)
                except Exception as error:
                    return error_handler(error, self, alias2)

        assert not isinstance(error_handler2, UndefinedType)
        serialized = SerializedMethod(func, conversion, schema, error_handler2)
        _serialized_methods[owner][alias2] = serialized

    if isinstance(__arg, str):
        alias = __arg
        __arg = None
    return method_registerer(__arg, owner, register)
