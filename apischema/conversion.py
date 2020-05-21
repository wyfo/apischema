import sys
from collections import defaultdict
from dataclasses import MISSING, dataclass, field
from inspect import Parameter, isclass, isgeneratorfunction, signature
from logging import getLogger
from types import MethodType
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Generic,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.properties import properties
from apischema.types import DictWithUnion, Metadata
from apischema.typing import _GenericAlias, get_type_hints
from apischema.utils import GeneratorValue, PREFIX, as_dict, to_camel_case
from apischema.validation.errors import build_from_errors
from apischema.visitor import NOT_CUSTOM, NotCustom

logger = getLogger(__name__)

Converter = Callable[[Any], Any]

_input_converters: Dict[Type, Dict[Type, Converter]] = defaultdict(dict)
_output_converters: Dict[Type, Tuple[Type, Converter]] = {}
_converters: Dict[Type, Dict[Type, Converter]] = defaultdict(dict)

Param = TypeVar("Param")
Return = TypeVar("Return")


def check_converter(
    converter: Converter, param: Optional[Type[Param]], ret: Optional[Type[Return]]
) -> Tuple[Type[Param], Type[Return]]:
    try:
        parameters = iter(signature(converter).parameters.values())
    except ValueError:  # builtin types
        if ret is None and isclass(ret):
            ret = cast(Type[Any], converter)
        if param is None:
            raise TypeError("converter parameter must be typed")
    else:
        try:
            first = next(parameters)
        except StopIteration:
            raise TypeError("converter must have at least one parameter")
        for p in parameters:
            if p.default is Parameter.empty and p.kind not in (
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
            ):
                raise TypeError(
                    "converter must have at most one parameter " "without default"
                )
        types = get_type_hints(converter, include_extras=True)
        if param is None:
            try:
                param = types.pop(first.name)
            except KeyError:
                raise TypeError("converter parameter must be typed")
        if ret is None:
            try:
                ret = types.pop("return")
            except KeyError:
                raise TypeError("converter return must be typed")
    return cast(Type[Param], param), cast(Type[Return], ret)


def handle_potential_validation(
    ret: Type, converter: Converter
) -> Tuple[Type, Converter]:
    if not isgeneratorfunction(converter):
        return ret, converter

    def wrapper(arg):
        generator = GeneratorValue(converter(arg))
        errors = [*generator]
        if errors:
            raise build_from_errors(errors)
        return generator.value

    if getattr(ret, "__origin__", None) == Generator:
        return ret.__args__[2], wrapper
    else:
        return ret, wrapper


Func = TypeVar("Func", bound=Callable)


class MethodConverter:
    def __init__(self, decorator: Callable, func: Callable):
        self.decorator = decorator
        self.func = func

    def __get__(self, instance, owner):
        return self if instance is None else MethodType(self.func, instance)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __set_name__(self, owner, name):
        self.decorator(self.func, owner)


def handle_method(decorator: Func) -> Func:
    def decorator2(func, param=None, ret=None):
        if param is None and ret is None:
            if list(signature(func).parameters)[0] == "self":
                return MethodConverter(decorator, func)
        return decorator(func, param, ret)

    return cast(Func, decorator2)


Cls = TypeVar("Cls", bound=Type)
Other = TypeVar("Other", bound=Type)

if sys.version_info >= (3, 7):
    import collections.abc
    import re
    from typing import (
        List,
        AbstractSet,
        Set,
        Dict,
        Iterable,
        Collection,
        Sequence,
        MutableSequence,
        Pattern,
    )

    TYPED_ORIGINS = {
        tuple: Tuple,
        list: List,
        frozenset: AbstractSet,
        set: Set,
        dict: Dict,
        collections.abc.Iterable: Iterable,
        collections.abc.Collection: Collection,
        collections.abc.Sequence: Sequence,
        collections.abc.MutableSequence: MutableSequence,
        collections.abc.Set: AbstractSet,
        collections.abc.MutableSet: Set,
        re.Pattern: Pattern,
    }

    def _get_origin(cls: _GenericAlias) -> Type:  # type: ignore
        return TYPED_ORIGINS.get(cls.__origin__, cls.__origin__)  # type: ignore


else:

    def _get_origin(cls: _GenericAlias) -> Type:  # type: ignore
        return cls.__origin__  # type: ignore


# If A[str, T] and A[T, int], what to choose for A[str, int]? None of them.


def substitute_generic_args(cls: Cls, substitution: Mapping) -> Cls:
    if getattr(cls, "__origin__", None) is None:
        return cls
    args = tuple(substitution.get(arg, arg) for arg in cls.__args__)
    return _get_origin(cls)[args]


def substitute_type_vars(base: Cls, other: Other) -> Tuple[Cls, Other]:
    if getattr(base, "__origin__", None) is None:
        return base, other
    substitution = {
        arg: param
        for arg, param in zip(base.__args__, _get_origin(base).__parameters__)
        if isinstance(arg, TypeVar)  # type: ignore
    }
    if isinstance(other, TypeVar):  # type: ignore
        new_other = substitution.get(other, other)
    else:
        new_other = substitute_generic_args(other, substitution)
    if all(isinstance(arg, TypeVar) for arg in base.__args__):  # type: ignore
        return cast(Tuple[Cls, Other], (_get_origin(base), new_other))
    else:
        return cast(
            Tuple[Cls, Other], (substitute_generic_args(base, substitution), new_other)
        )


@handle_method
def converter(function: Func, param: Type = None, ret: Type = None) -> Func:
    param, ret = check_converter(function, param, ret)
    param, ret = substitute_type_vars(param, ret)
    _converters[param][ret] = function
    return function


@handle_method
def input_converter(function: Func, param: Type = None, ret: Type = None) -> Func:
    param, ret = check_converter(function, param, ret)
    ret, function_ = handle_potential_validation(ret, function)
    ret, param = substitute_type_vars(ret, param)
    _input_converters[ret][param] = function_
    return function


@handle_method
def output_converter(function: Func, param: Type = None, ret: Type = None) -> Func:
    param, ret = check_converter(function, param, ret)
    param, ret = substitute_type_vars(param, ret)
    _output_converters[param] = ret, function
    _converters[param][ret] = function
    return function


def inout_model(model: Type, *, replace_new_type: bool = True) -> Callable[[Cls], Cls]:
    def decorator(cls: Cls) -> Cls:
        input_converter(cls, model, cls)
        out_conv = model
        if replace_new_type and hasattr(model, "__supertype__"):
            out_conv = model.__supertype__
        output_converter(out_conv, cls, model)
        return cls

    return decorator


Arg = TypeVar("Arg")


class InputVisitorMixin(Generic[Arg, Return]):
    def _custom(self, cls: Type, custom: Dict[Type, Converter], arg: Arg) -> Return:
        raise NotImplementedError()

    def custom(self, cls: Type, arg: Arg) -> Union[Return, NotCustom]:
        if cls not in _input_converters:
            return NOT_CUSTOM
        return self._custom(cls, _input_converters[cls], arg)


class OutputVisitorMixin(Generic[Arg, Return]):
    def __init__(self, conversions: Mapping[Type, Type]):
        self.converters = {}
        for cls, out in conversions.items():
            cls, out = substitute_type_vars(cls, out)
            if out not in _converters.get(cls, {}):
                logger.warning(f"{cls} cannot be converted to {out}")
            else:
                self.converters[cls] = out, _converters[cls][out]

    def _custom(self, cls: Type, custom: Tuple[Type, Converter], arg: Arg) -> Return:
        raise NotImplementedError()

    def custom(self, cls: Type, arg: Arg) -> Union[Return, NotCustom]:
        if cls in self.converters:
            return self._custom(cls, self.converters[cls], arg)
        if cls in _output_converters:
            return self._custom(cls, _output_converters[cls], arg)
        return NOT_CUSTOM


INPUT_METADATA = f"{PREFIX}input"
OUTPUT_METADATA = f"{PREFIX}output"


def field_input_converter(
    converter: Callable[[Any], Any], param: Type = None, ret: Type = None
) -> Metadata:
    try:
        param, ret = check_converter(converter, param, ret)
    except NameError:
        pass
    else:
        ret, converter = handle_potential_validation(ret, converter)
    return DictWithUnion({INPUT_METADATA: (param, converter)})


def field_output_converter(
    converter: Callable[[Any], Any], param: Type = None, ret: Type = None
) -> Metadata:
    try:
        param, ret = check_converter(converter, param, ret)
    except NameError:
        pass
    return DictWithUnion({OUTPUT_METADATA: (ret, converter)})


def converter_from_raw(func: Callable) -> Converter:
    types = get_type_hints(func, include_extras=True)
    sig = signature(func)
    annotations: Dict[str, Any] = {}
    fields: Dict[str, Any] = {}
    kwargs = None
    for name, param in sig.parameters.items():
        if param.kind == Parameter.POSITIONAL_ONLY:
            raise TypeError("Forbidden positional-only parameter")
        if param.kind == Parameter.VAR_POSITIONAL:
            raise TypeError("Forbidden variadic positional parameter")
        if param.kind == Parameter.VAR_KEYWORD:
            fields[name] = field(
                default_factory=dict,  # type: ignore
                metadata=properties(),
            )
            type_ = types.get(name, Any)
            annotations[name] = Mapping[str, type_]  # type: ignore
            kwargs = name
            continue
        try:
            default = MISSING
            if param.default != Parameter.empty:
                default = param.default
            fields[name] = default
            annotations[name] = types[name]
        except KeyError:
            raise TypeError("All parameters must be annotated")

    def converter(obj):
        kw = as_dict(obj)
        kw.update(kw.pop(kwargs, ()))
        return func(**kw)

    namespace = {**fields, "__annotations__": annotations}  # type: ignore
    cls: Type = dataclass(type(to_camel_case(func.__name__), (), namespace))
    converter.__annotations__ = {"obj": cls, "return": types.get("return")}
    return converter


def raw_input_converter(func: Func) -> Func:
    input_converter(converter_from_raw(func))
    return func


def raw_field_input_converter(func: Callable) -> Metadata:
    return field_input_converter(raw_input_converter(func))
