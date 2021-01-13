from enum import Enum, auto
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.types import AnyType
from apischema.typing import _GenericAlias, get_origin

PREFIX = "_apischema_"


# Singleton type, see https://www.python.org/dev/peps/pep-0484/#id30
class UndefinedType(Enum):
    def __repr__(self):
        return "Undefined"

    def __str__(self):
        return "Undefined"

    def __bool__(self):
        return False

    Undefined = auto()


Undefined = UndefinedType.Undefined


def is_hashable(obj) -> bool:
    try:
        hash(obj)
    except Exception:  # should be TypeError, but who knows what can happen
        return False
    else:
        return True


def to_hashable(data: Union[None, int, float, str, bool, list, dict]) -> Hashable:
    if isinstance(data, list):
        return tuple(map(to_hashable, data))
    if isinstance(data, dict):
        return tuple(sorted((to_hashable(k), to_hashable(v)) for k, v in data.items()))
    return data  # type: ignore


def to_camel_case(s: str):
    pascal_case = "".join(map(str.capitalize, s.split("_")))
    return pascal_case[0].lower() + pascal_case[1:]


_type_hints: Dict[str, Mapping[str, Type]] = {}


def type_name(cls: AnyType) -> str:
    if hasattr(cls, "__name__"):
        return cls.__name__
    elif isinstance(cls, _GenericAlias):
        return cls._name
    else:
        raise NotImplementedError()


MakeDataclassField = Union[Tuple[str, AnyType], Tuple[str, AnyType, Any]]

T = TypeVar("T")


def merge_opts(
    func: Callable[[T, T], T]
) -> Callable[[Optional[T], Optional[T]], Optional[T]]:
    def wrapper(opt1, opt2):
        if opt1 is None:
            return opt2
        if opt2 is None:
            return opt1
        return func(opt1, opt2)

    return wrapper


K = TypeVar("K")
V = TypeVar("V")


@merge_opts
def merge_opts_mapping(m1: Mapping[K, V], m2: Mapping[K, V]) -> Mapping[K, V]:
    return {**m1, **m2}


def is_type_var(cls: AnyType) -> bool:
    return isinstance(cls, TypeVar)  # type: ignore


Func = TypeVar("Func", bound=Callable)


def typed_wraps(wrapped: Func) -> Callable[[Callable], Func]:
    return cast(Func, wraps(wrapped))


def get_origin_or_class(cls: AnyType) -> Type:
    origin = get_origin(cls)
    return origin if origin is not None else cls


class Operation(Enum):
    DESERIALIZATION = auto()
    SERIALIZATION = auto()


MethodOrProperty = Union[Callable, property]


def is_method(func: MethodOrProperty) -> bool:
    """Return if the function is method/property declared in a class"""
    return isinstance(func, property) or func.__name__ != func.__qualname__


def method_wrapper(method: MethodOrProperty, name: str) -> Callable:
    wrapper: Callable
    if isinstance(method, property):

        @wraps(method.fget)
        def wrapper(self):
            return getattr(self, name)

    else:

        @wraps(method.__get__(None, object))  # type: ignore
        def wrapper(self, *args, **kwargs):

            return getattr(self, name)(*args, **kwargs)

    return wrapper


try:
    from functools import cached_property
except ImportError:
    # From 3.9 functools
    from threading import RLock

    _NOT_FOUND = object()

    class cached_property:  # type: ignore
        def __init__(self, func):
            self.func = func
            self.attrname = None
            self.__doc__ = func.__doc__
            self.lock = RLock()

        def __set_name__(self, owner, name):
            if self.attrname is None:
                self.attrname = name
            elif name != self.attrname:
                raise TypeError(
                    "Cannot assign the same cached_property to two different names "
                    f"({self.attrname!r} and {name!r})."
                )

        def __get__(self, instance, owner=None):
            if instance is None:
                return self
            if self.attrname is None:
                raise TypeError(
                    "Cannot use cached_property instance"
                    " without calling __set_name__ on it."
                )
            try:
                cache = instance.__dict__
            except AttributeError:  # not all objects have __dict__ (e.g. class defines slots) # noqa: E501
                msg = (
                    f"No '__dict__' attribute on {type(instance).__name__!r} "
                    f"instance to cache {self.attrname!r} property."
                )
                raise TypeError(msg) from None
            val = cache.get(self.attrname, _NOT_FOUND)
            if val is _NOT_FOUND:
                with self.lock:
                    # check if another thread filled cache while we awaited lock
                    val = cache.get(self.attrname, _NOT_FOUND)
                    if val is _NOT_FOUND:
                        val = self.func(instance)
                        try:
                            cache[self.attrname] = val
                        except TypeError:
                            msg = (
                                f"The '__dict__' attribute on"
                                f" {type(instance).__name__!r} instance "
                                f"does not support item assignment for"
                                f" caching {self.attrname!r} property."
                            )
                            raise TypeError(msg) from None
            return val

        __class_getitem__ = classmethod(_GenericAlias)
