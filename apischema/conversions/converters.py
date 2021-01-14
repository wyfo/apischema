from collections import defaultdict
from functools import wraps
from types import new_class
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    NewType,
    Optional,
    Pattern,
    Sequence,
    TYPE_CHECKING,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.conversions.utils import (
    Conversions,
    ConverterWithConversions,
    check_converter,
    check_convertible,
    handle_generic_conversions,
)
from apischema.types import AnyType, OrderedDict
from apischema.utils import Undefined, is_method, to_camel_case

if TYPE_CHECKING:
    from apischema.json_schema.annotations import Deprecated

_deserializers: Dict[AnyType, Dict[AnyType, ConverterWithConversions]] = defaultdict(
    OrderedDict
)
_extra_deserializers: Dict[
    AnyType, Dict[AnyType, ConverterWithConversions]
] = defaultdict(OrderedDict)
_serializers: Dict[Type, Tuple[Type, ConverterWithConversions]] = {}
_extra_serializers: Dict[Type, Dict[Type, ConverterWithConversions]] = defaultdict(dict)

Func = TypeVar("Func", bound=Callable)
_ConverterSetter = Callable[[Func, AnyType, AnyType, Optional[Conversions], bool], Func]


class MethodConverter:
    def __init__(
        self,
        decorator: _ConverterSetter,
        method: Union[Callable, property, staticmethod],
        conversions: Optional[Conversions],
        extra: bool,
    ):
        self.decorator = decorator
        self.method = method
        self.conversions = conversions
        self.extra = extra

    def __call__(self, *args, **kwargs):
        raise RuntimeError("Converter method __set_name__ has not been called")

    def __set_name__(self, owner, name):
        if isinstance(self.method, property):
            converter = wraps(self.method.fget)(lambda obj: getattr(obj, name))
        elif isinstance(self.method, staticmethod):
            converter = self.method.__get__(None, object)
        else:
            converter = wraps(self.method)(lambda obj: getattr(obj, name)())
        param = None if isinstance(self.method, staticmethod) else owner
        param, ret = check_converter(converter, param, None, {owner.__name__: owner})
        self.decorator(converter, param, ret, self.conversions, self.extra)
        setattr(owner, name, self.method)


try:
    from apischema.typing import Protocol

    class ConverterSetter(Protocol[Func]):
        @overload
        def __call__(
            self,
            function: Func,
            param: AnyType = None,
            ret: AnyType = None,
            conversions: Conversions = None,
        ) -> Func:
            ...

        @overload
        def __call__(self, *, conversions: Conversions) -> Callable[[Func], Func]:
            ...

        def __call__(
            self,
            function: Func = None,
            param: AnyType = None,
            ret: AnyType = None,
            conversions: Conversions = None,
        ):
            ...


except ImportError:
    ConverterSetter = Callable  # type: ignore


def _converter(decorator: _ConverterSetter, *, extra: bool) -> ConverterSetter:
    def wrapper(
        func: Callable = None,
        param: AnyType = None,
        ret: AnyType = None,
        conversions: Conversions = None,
    ):
        if func is None:
            return lambda func: wrapper(func, param, ret, conversions)
        if isinstance(func, classmethod):
            raise TypeError("classmethod cannot be used as a converter")
        if isinstance(func, (property, staticmethod)):
            return MethodConverter(decorator, func, conversions, extra)
        try:
            param, ret = check_converter(func, param, ret)
            return decorator(func, param, ret, conversions, extra)
        except Exception:  # param is not annotated or recursive
            if is_method(func):
                return MethodConverter(decorator, func, conversions, extra)
            else:
                raise

    return cast(ConverterSetter, wrapper)


def _deserializer(
    function: Func,
    param: AnyType,
    ret: AnyType,
    conversions: Optional[Conversions],
    extra: bool,
) -> Func:
    ret, param = handle_generic_conversions(ret, param)
    check_convertible(ret)
    if param == ret:
        raise ValueError("Use self_deserializer")
    _extra_deserializers[ret][param] = function, conversions
    if not extra:
        _deserializers[ret][param] = function, conversions
    return function


deserializer = _converter(_deserializer, extra=False)
extra_deserializer = _converter(_deserializer, extra=True)


def _serializer(
    function: Func,
    param: Type,
    ret: AnyType,
    conversions: Optional[Conversions],
    extra: bool,
) -> Func:
    param, ret = handle_generic_conversions(param, ret)
    check_convertible(param)
    if param == ret:
        if conversions:
            raise ValueError("Self-conversions cannot have conversions parameter")
        if not extra:
            _serializers.pop(param, ...)
    else:
        _extra_serializers[param][ret] = (function, conversions)
        if not extra:
            _serializers[param] = ret, (function, conversions)
    return function


serializer = _converter(_serializer, extra=False)
extra_serializer = _converter(_serializer, extra=True)


Cls = TypeVar("Cls", bound=Type)


def self_deserializer(cls: Cls) -> Cls:
    _deserializer(lambda x: x, new_class(cls.__name__, (cls,)), cls, None, extra=False)
    return cls


def reset_deserializers(cls: AnyType):
    _deserializers.pop(cls, ...)


class InheritedDeserializer:
    def __init__(
        self, method: classmethod, conversions: Optional[Conversions], extra: bool
    ):
        self.method = method
        self.conversions = conversions
        self.extra = extra

    def __set_name__(self, owner, name):
        prev_init_subclass = owner.__init_subclass__

        def init_subclass(cls, **kwargs):
            prev_init_subclass(**kwargs)
            deserializer(getattr(cls, name), None, cls)

        owner.__init_subclass__ = classmethod(init_subclass)
        converter = self.method.__get__(None, owner)
        param, ret = check_converter(converter, None, owner, {owner.__name__: owner})
        _deserializer(converter, param, ret, self.conversions, self.extra)
        setattr(owner, name, self.method)


ClsMethod = TypeVar("ClsMethod")


@overload
def inherited_deserializer(func: ClsMethod) -> ClsMethod:
    ...


@overload
def inherited_deserializer(
    *, conversions: Conversions = None, extra: bool = False
) -> Callable[[ClsMethod], ClsMethod]:
    ...


def inherited_deserializer(
    func=None, *, conversions: Conversions = None, extra: bool = False
):
    if func is None:
        return lambda func: inherited_deserializer(  # type: ignore
            func, conversions=conversions
        )
    if not isinstance(func, classmethod):
        raise TypeError("inherited_deserializer must be called on classmethod")
    return InheritedDeserializer(func, conversions, extra)


def as_str(
    cls: Cls,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default: Any = Undefined,
    examples: Optional[Sequence[Any]] = None,
    deprecated: "Deprecated" = False,
    format: Optional[str] = None,
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    pattern: Optional[Union[str, Pattern]] = None,
    extra: Mapping[str, Any] = None,
    override: bool = False,
) -> Cls:
    ...


@wraps(as_str)
def _as_str(cls: Type, **kwargs):
    from apischema import schema

    str_type = schema(**kwargs)(NewType(to_camel_case(cls.__name__), str))
    deserializer(cls, str_type, cls)
    serializer(str, cls, str_type)


globals()[as_str.__name__] = _as_str
