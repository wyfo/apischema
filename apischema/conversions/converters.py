from collections import defaultdict
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
    Type,
    TypeVar,
    overload,
)

from apischema.conversions.conversions import (
    Conversion,
    Conversions,
    resolve_deserialization,
    resolve_serialization,
)
from apischema.conversions.utils import converter_types
from apischema.utils import (
    MethodOrProperty,
    MethodWrapper,
    is_method,
    method_class,
    method_wrapper,
)

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coercion


_deserializers: Dict[Type, List[Conversion]] = defaultdict(list)
_serializers: Dict[Type, Conversion] = {}
Deserializer = TypeVar("Deserializer", Callable, Conversion, staticmethod, type)
Serializer = TypeVar("Serializer", Callable, Conversion, property, type)


class DeserializerDescriptor(MethodWrapper[staticmethod]):
    def __init__(self, method: staticmethod, **kwargs):
        super().__init__(method)
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        method = self._method.__get__(None, object)
        source, target = converter_types(method, namespace={owner.__name__: owner})
        conversion = Conversion(method, source=source, target=target, **self._kwargs)
        resolved = resolve_deserialization(conversion)
        if resolved not in _deserializers[resolved.source]:
            _deserializers[resolved.target] = conversion


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
        arg = Conversion(arg, **kwargs)
    resolved = resolve_deserialization(arg)
    if resolved not in _deserializers[resolved.target]:
        _deserializers[resolved.target].append(arg)
    return arg


class SerializerDescriptor(MethodWrapper[MethodOrProperty]):
    def __init__(self, method: MethodOrProperty, **kwargs):
        super().__init__(method)
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        method = method_wrapper(self._method, name)
        source, target = converter_types(
            method, source=owner, namespace={owner.__name__: owner}
        )
        conversion = Conversion(method, source=source, target=target, **self._kwargs)
        _serializers[resolve_serialization(conversion).source] = conversion


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
        arg = Conversion(arg, **kwargs)
    _serializers[resolve_serialization(arg).source] = arg
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
