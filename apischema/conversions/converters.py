from collections import defaultdict
from contextlib import suppress
from functools import wraps
from inspect import signature
from typing import (
    Callable,
    Dict,
    Optional,
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
        method: Union[Callable, classmethod, staticmethod],
        conversions: Optional[Conversions],
        extra: bool,
        instance_method: bool,
    ):
        self.decorator = decorator
        self.method = method
        self.conversions = conversions
        self.extra = extra
        self.instance_method = instance_method

    def __call__(self, *args, **kwargs):
        raise RuntimeError(
            f"Converter method {self.method} __set_name__ has not been called"
        )

    @staticmethod
    def _return(owner: Type) -> Optional[Type]:
        return None

    def __set_name__(self, owner, name):
        converter = self.method.__get__(None, owner)
        if self.instance_method:
            converter = wraps(converter)(lambda instance: getattr(instance, name)())
        param = owner if self.instance_method else None
        param, ret = check_converter(
            converter, param, self._return(owner), {owner.__name__: owner}
        )
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
        if isinstance(func, (classmethod, staticmethod)):
            return MethodConverter(
                decorator, func, conversions, extra, instance_method=False
            )
        if param is None:
            with suppress(ValueError):  # builtin type has no signature
                first_param = next(iter(signature(func).parameters.values()), None)
                if first_param is not None and first_param.name == "self":
                    try:
                        param, ret = check_converter(func, param, ret)
                        return decorator(func, param, ret, conversions, extra)
                    except Exception:  # param is not annotated or recursive
                        return MethodConverter(
                            decorator, func, conversions, extra, instance_method=True
                        )
        param, ret = check_converter(func, param, ret)
        return decorator(func, param, ret, conversions, extra)

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
    _deserializer(lambda x: x, type(cls.__name__, (cls,), {}), cls, None, extra=False)
    return cls


def reset_deserializers(cls: AnyType):
    _deserializers.pop(cls, ...)


class InheritedDeserializer(MethodConverter):
    def __init__(
        self, method: classmethod, conversions: Optional[Conversions], extra: bool
    ):
        super().__init__(_deserializer, method, conversions, extra, False)

    @staticmethod
    def _return(owner: Type) -> Optional[Type]:
        return owner

    def __set_name__(self, owner, name):
        prev_init_subclass = owner.__init_subclass__

        def init_subclass(cls, **kwargs):
            prev_init_subclass(**kwargs)
            deserializer(getattr(cls, name), None, cls)

        owner.__init_subclass__ = classmethod(init_subclass)
        super().__set_name__(owner, name)


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
