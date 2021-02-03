from collections import defaultdict
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
    method_wrapper,
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


def _add_deserializer(conversion: Union[Converter, Conversion], owner: Type = None):
    namespace = {owner.__name__: owner} if owner is not None else None
    resolved = resolve_conversion(conversion, namespace)
    target = check_converter_type(resolved.target, "deserializer target")
    if conversion not in _deserializers[target]:
        _deserializers[target].append(conversion)


class DeserializerDescriptor(MethodWrapper[staticmethod]):
    def __init__(self, method: staticmethod, **kwargs):
        super().__init__(method)
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        _add_deserializer(
            Conversion(self._method.__get__(None, object), **self._kwargs), owner
        )


@overload
def deserializer(arg: Deserializer) -> Deserializer:
    ...


@overload
def deserializer(
    *,
    conversions: Conversions = None,
    additional_properties: Optional[bool] = None,
    coercion: Optional["Coercion"] = None,
    default_fallback: Optional[bool] = None,
) -> Callable[[Serializer], Serializer]:
    ...


def deserializer(arg=None, **kwargs):
    if arg is None:
        return lambda arg: deserializer(arg, **kwargs)  # type: ignore
    if isinstance(arg, staticmethod):
        return DeserializerDescriptor(arg, **kwargs)
    if kwargs and not isinstance(arg, Conversion):
        _add_deserializer(Conversion(arg, **kwargs))
    else:
        _add_deserializer(arg)
    return arg


def _add_serializer(conversion: Union[Converter, Conversion], owner: Type = None):
    namespace = {owner.__name__: owner} if owner is not None else None
    resolved = resolve_conversion(conversion, namespace)
    source = check_converter_type(resolved.source, "serializer source")
    _serializers[source] = conversion


class SerializerDescriptor(MethodWrapper[MethodOrProperty]):
    def __init__(self, method: MethodOrProperty, **kwargs):
        super().__init__(method)
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        _add_serializer(Conversion(self._method, source=owner, **self._kwargs), owner)


@overload
def serializer(arg: Serializer) -> Serializer:
    ...


@overload
def serializer(
    *,
    conversions: Conversions = None,
    exclude_unset: bool = None,
) -> Callable[[Serializer], Serializer]:
    ...


def serializer(arg=None, **kwargs):
    if arg is None:
        return lambda arg: serializer(arg, **kwargs)  # type: ignore
    if is_method(arg):
        if method_class(arg) is None:
            return SerializerDescriptor(arg, **kwargs)
        else:
            arg = method_wrapper(arg)
    if kwargs and not isinstance(arg, Conversion):
        _add_serializer(Conversion(arg, **kwargs))
    else:
        _add_serializer(arg)
    return arg


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
    conversions: Conversions = None,
    additional_properties: Optional[bool] = None,
    coercion: Optional["Coercion"] = None,
    default_fallback: Optional[bool] = None,
) -> Callable[[ClsMethod], ClsMethod]:
    ...


def inherited_deserializer(method=None, **kwargs):
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
