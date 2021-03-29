import warnings
from collections import defaultdict
from dataclasses import replace
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
    Type,
    TypeVar,
    Union,
    overload,
)

from apischema.conversions import LazyConversion
from apischema.conversions.conversions import (
    ConvOrFunc,
    Conversion,
    Conversions,
    resolve_conversion,
)
from apischema.conversions.utils import Converter, INVALID_CONVERSION_TYPES
from apischema.types import AnyType
from apischema.utils import (
    MethodOrProperty,
    MethodWrapper,
    get_args2,
    get_origin_or_type,
    is_method,
    is_type_var,
    method_class,
    stop_signature_abuse,
)

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coercion


_deserializers: Dict[Type, List[ConvOrFunc]] = defaultdict(list)
_serializers: Dict[Type, ConvOrFunc] = {}
Deserializer = TypeVar("Deserializer", Callable, Conversion, staticmethod, type)
Serializer = TypeVar("Serializer", Callable, Conversion, property, type)


def check_converter_type(tp: AnyType, side: str) -> Type:
    if not all(map(is_type_var, get_args2(tp))):
        raise TypeError("Generic conversion doesn't support specialization")
    origin = get_origin_or_type(tp)
    if not isinstance(origin, type) or origin in INVALID_CONVERSION_TYPES:
        raise TypeError(f"{side.capitalize()} must be a class")
    return origin


def _add_deserializer(conversion: ConvOrFunc, target: AnyType):
    target = check_converter_type(target, "deserializer target")
    if conversion not in _deserializers[target]:
        _deserializers[target].append(conversion)


class DeserializerDescriptor(MethodWrapper[staticmethod]):
    def __init__(self, method: staticmethod, **kwargs):
        super().__init__(method)
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        method = self._method.__get__(None, object)
        target = resolve_conversion(method, {owner.__name__: owner})
        _add_deserializer(method, target)


@overload
def deserializer(deserializer: Deserializer) -> Deserializer:
    ...


@overload
def deserializer(
    *, lazy: Callable[[], Union[Converter, Conversion]], target: Type
) -> None:
    ...


def deserializer(
    deserializer: Deserializer = None,
    *,
    lazy: Callable[[], Union[Converter, Conversion]] = None,
    target: Type = None,
):
    if deserializer is not None:
        if isinstance(deserializer, staticmethod):
            return DeserializerDescriptor(deserializer)
        elif isinstance(deserializer, LazyConversion):
            stop_signature_abuse()
        else:
            resolved = resolve_conversion(deserializer)
            _add_deserializer(deserializer, resolved.target)
            return deserializer
    elif lazy is not None and target is not None:

        def replace_target():
            conversion = lazy()
            if isinstance(conversion, Conversion):
                return replace(conversion, target=target)
            else:
                return Conversion(conversion, target=target)

        _add_deserializer(LazyConversion(replace_target), target)
    else:
        stop_signature_abuse()


def _add_serializer(conversion: ConvOrFunc, source: AnyType):
    source = check_converter_type(source, "serializer source")
    _serializers[source] = conversion


class SerializerDescriptor(MethodWrapper[MethodOrProperty]):
    def __init__(self, method: MethodOrProperty, **kwargs):
        super().__init__(method)
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        _add_serializer(self._method, source=owner)


@overload
def serializer(serializer: Serializer) -> Serializer:
    ...


@overload
def serializer(
    *, lazy: Callable[[], Union[Converter, Conversion]], source: Type
) -> Callable[[Serializer], Serializer]:
    ...


def serializer(
    serializer: Serializer = None,
    *,
    lazy: Callable[[], Union[Converter, Conversion]] = None,
    source: Type = None,
):
    if serializer is not None:
        if is_method(serializer) and method_class(serializer) is None:
            return SerializerDescriptor(serializer)
        elif isinstance(serializer, LazyConversion):
            stop_signature_abuse()
        else:
            resolved = resolve_conversion(serializer)
            _add_serializer(serializer, resolved.source)
            return serializer
    elif lazy is not None and source is not None:

        def replace_source():
            conversion = lazy()
            if isinstance(conversion, Conversion):
                return replace(conversion, source=source)
            else:
                return Conversion(conversion, source=source)

        _add_serializer(LazyConversion(replace_source), source)
    else:
        stop_signature_abuse()


def reset_deserializers(cls: Type):
    _deserializers.pop(cls, ...)


def reset_serializer(cls: Type):
    _deserializers.pop(cls, ...)


class InheritedDeserializer:
    def __init__(self, method: classmethod, **kwargs):
        self.method = method
        self.kwargs = kwargs

    def __set_name__(self, owner, name):
        prev_init_subclass = owner.__init_subclass__

        def init_subclass(cls, **kwargs):
            prev_init_subclass(**kwargs)
            method = self.method.__get__(None, cls)
            deserializer(Conversion(method, target=cls, **self.kwargs))

        owner.__init_subclass__ = classmethod(init_subclass)
        init_subclass(owner)
        setattr(owner, name, self.method)


ClsMethod = TypeVar("ClsMethod")


@overload
def inherited_deserializer(method: ClsMethod) -> ClsMethod:
    ...


@overload
def inherited_deserializer(
    *,
    sub_conversions: Conversions = None,
    additional_properties: Optional[bool] = None,
    coercion: Optional["Coercion"] = None,
    default_fallback: Optional[bool] = None,
) -> Callable[[ClsMethod], ClsMethod]:
    ...


def inherited_deserializer(method=None, **kwargs):
    warnings.warn(
        "inherited_deserializer is deprecated; __init_subclasses", DeprecationWarning
    )
    if method is None:
        return lambda func: inherited_deserializer(func, **kwargs)  # type: ignore
    if not isinstance(method, classmethod):
        raise TypeError("inherited_deserializer must be called on classmethod")
    return InheritedDeserializer(method, **kwargs)


Cls = TypeVar("Cls", bound=Type)


def as_str(cls: Cls) -> Cls:
    deserializer(Conversion(cls, source=str))
    serializer(Conversion(str, source=cls))
    return cls
