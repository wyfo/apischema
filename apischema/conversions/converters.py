import sys
from collections import defaultdict
from enum import Enum
from functools import partial, wraps
from types import new_class
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    MutableMapping,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.cache import CacheAwareDict
from apischema.conversions import LazyConversion
from apischema.conversions.conversions import (
    AnyConversion,
    Conversion,
    ConvOrFunc,
    resolve_conversion,
)
from apischema.conversions.utils import Converter, is_convertible
from apischema.methods import MethodOrProperty, MethodWrapper, is_method, method_class
from apischema.type_names import type_name
from apischema.types import AnyType
from apischema.typing import is_type_var
from apischema.utils import get_args2, get_origin_or_type, stop_signature_abuse
from apischema.validation.errors import ValidationError

if TYPE_CHECKING:
    pass


_deserializers: MutableMapping[AnyType, List[ConvOrFunc]] = CacheAwareDict(
    defaultdict(list)
)
_serializers: MutableMapping[AnyType, ConvOrFunc] = CacheAwareDict({})
Deserializer = TypeVar(
    "Deserializer", bound=Union[Callable, Conversion, staticmethod, type]
)
Serializer = TypeVar("Serializer", bound=Union[Callable, Conversion, property, type])

default_deserialization: Callable[[type], Optional[AnyConversion]]
# defaultdict.get is not hashable in 3.7
if sys.version_info < (3, 8):

    def default_deserialization(tp):
        return _deserializers.get(tp)

else:
    default_deserialization = _deserializers.get  # type: ignore


def default_serialization(tp: Type) -> Optional[AnyConversion]:
    for sub_cls in getattr(tp, "__mro__", [tp]):
        if sub_cls in _serializers:
            conversion = _serializers[sub_cls]
            if (
                sub_cls == tp
                or not isinstance(conversion, (Conversion, LazyConversion))
                or conversion.inherited in (None, True)
            ):
                return conversion
    else:
        return None


def check_converter_type(tp: AnyType) -> AnyType:
    origin = get_origin_or_type(tp)
    if not is_convertible(tp):
        raise TypeError(f"{origin} is not convertible")
    if not all(map(is_type_var, get_args2(tp))):
        raise TypeError("Generic conversion doesn't support specialization")
    return origin


def _add_deserializer(conversion: ConvOrFunc, target: AnyType):
    target = check_converter_type(target)
    if conversion not in _deserializers[target]:
        _deserializers[target].append(conversion)


class DeserializerDescriptor(MethodWrapper[staticmethod]):
    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        method = self._method.__get__(None, object)
        resolved = resolve_conversion(method, {owner.__name__: owner})
        _add_deserializer(method, resolved.target)


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
        _add_deserializer(LazyConversion(lazy), target)
    else:
        stop_signature_abuse()


def _add_serializer(conversion: ConvOrFunc, source: AnyType):
    source = check_converter_type(source)
    _serializers[source] = conversion


class SerializerDescriptor(MethodWrapper[MethodOrProperty]):
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
        if is_method(serializer) and method_class(serializer) is None:  # type: ignore
            return SerializerDescriptor(serializer)  # type: ignore
        elif isinstance(serializer, LazyConversion):
            stop_signature_abuse()
        else:
            resolved = resolve_conversion(serializer)
            _add_serializer(serializer, resolved.source)
            return serializer
    elif lazy is not None and source is not None:
        _add_serializer(LazyConversion(lazy), source)
    else:
        stop_signature_abuse()


def reset_deserializers(cls: Type):
    _deserializers.pop(cls, ...)


def reset_serializer(cls: Type):
    _serializers.pop(cls, ...)


Func = TypeVar("Func", bound=Callable)


class ValueErrorCatcher:
    def __init__(self, func: Callable[[Any], Any]):
        wraps(func)(self)
        self.func = func

    def __call__(self, arg):
        try:
            return self.func(arg)
        except ValueError as err:
            raise ValidationError(str(err))


def catch_value_error(func: Func) -> Func:
    return cast(Func, ValueErrorCatcher(func))


Cls = TypeVar("Cls", bound=type)


def as_str(cls: Cls) -> Cls:
    deserializer(Conversion(catch_value_error(cls), source=str, target=cls))
    serializer(Conversion(str, source=cls))
    return cls


EnumCls = TypeVar("EnumCls", bound=Type[Enum])


def as_names(cls: EnumCls, aliaser: Callable[[str], str] = lambda s: s) -> EnumCls:
    # Enum requires to call namespace __setitem__
    def exec_body(namespace: dict):
        for elt in cls:  # type: ignore
            namespace[elt.name] = aliaser(elt.name)

    if not issubclass(cls, Enum):
        raise TypeError("as_names must be called with Enum subclass")
    name_cls = type_name(None)(
        new_class(cls.__name__, (str, Enum), exec_body=exec_body)
    )
    deserializer(Conversion(partial(getattr, cls), source=name_cls, target=cls))

    def get_name(obj):
        return getattr(name_cls, obj.name)

    serializer(Conversion(get_name, source=cls, target=name_cls))
    return cls
