import collections.abc
import re
from enum import Enum, auto
from functools import wraps
from inspect import signature
from types import FunctionType
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Generic,
    Hashable,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    OrderedDict,
    subscriptable_origin,
)
from apischema.typing import _GenericAlias, _collect_type_vars, get_args, get_origin

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

PREFIX = "_apischema_"

T = TypeVar("T")
U = TypeVar("U")


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


def opt_or(opt: Optional[T], default: U) -> Union[T, U]:
    return opt if opt is not None else default


def to_hashable(data: Union[None, int, float, str, bool, list, dict]) -> Hashable:
    if isinstance(data, list):
        return tuple(map(to_hashable, data))
    if isinstance(data, dict):
        return tuple(sorted((to_hashable(k), to_hashable(v)) for k, v in data.items()))
    return data  # type: ignore


def contains(collection: Collection[T], obj: T) -> bool:
    try:
        return obj in collection
    except TypeError:
        return False


SNAKE_CASE_REGEX = re.compile(r"_([a-z\d])")


def to_camel_case(s: str):
    return SNAKE_CASE_REGEX.sub(lambda m: m.group(1).upper(), s)


MakeDataclassField = Union[Tuple[str, AnyType], Tuple[str, AnyType, Any]]


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


def is_type_var(tp: AnyType) -> bool:
    return isinstance(tp, TypeVar)  # type: ignore


def has_type_vars(tp: AnyType) -> bool:
    return is_type_var(tp) or bool(getattr(tp, "__parameters__", ()))


TV = AnyType  # TypeVar is not supported as a type
# 10 should be enough for all builtin types
_type_vars = [TypeVar(f"T{i}") for i in range(10)]


def get_parameters(tp: AnyType) -> Iterable[TV]:
    if hasattr(tp, "__parameters__"):
        return tp.__parameters__
    elif hasattr(tp, "__orig_bases__"):
        return _collect_type_vars(tp.__orig_bases__)
    else:
        return _type_vars


def substitute_type_vars(tp: AnyType, substitution: Mapping[TV, AnyType]) -> AnyType:
    if is_type_var(tp):
        try:
            return substitution[tp]
        except KeyError:
            return Union[tp.__constraints__] if tp.__constraints__ else Any
    elif getattr(tp, "__parameters__", ()):
        return tp[tuple(substitution.get(p, p) for p in tp.__parameters__)]
    else:
        return tp


Func = TypeVar("Func", bound=Callable)


def typed_wraps(wrapped: Func) -> Callable[[Callable], Func]:
    return cast(Func, wraps(wrapped))


def get_origin2(tp: AnyType) -> Optional[Type]:
    origin = get_origin(tp)
    return get_origin(get_args(tp)[0]) if origin is Annotated else origin


def get_args2(tp: AnyType) -> Tuple[AnyType, ...]:
    origin = get_origin(tp)
    return get_args(get_args(tp)[0]) if origin is Annotated else get_args(tp)


def get_origin_or_type(tp: AnyType) -> Type:
    origin = get_origin(tp)
    if origin is Annotated:
        return get_origin_or_type(get_args(tp)[0])
    return origin if origin is not None else tp


def is_union_of(tp: AnyType, of: AnyType) -> bool:
    return tp == of or (get_origin_or_type(tp) == Union and of in get_args2(tp))


class OperationKind(Enum):
    DESERIALIZATION = auto()
    SERIALIZATION = auto()


MethodOrProperty = Union[Callable, property]


def _method_location(method: MethodOrProperty) -> Optional[Type]:
    if isinstance(method, property):
        method = method.fget
    while hasattr(method, "__wrapped__"):
        method = method.__wrapped__  # type: ignore
    assert isinstance(method, FunctionType)
    global_name, *class_path = method.__qualname__.split(".")[:-1]
    if global_name not in method.__globals__:
        return None
    location = method.__globals__[global_name]
    for attr in class_path:
        if hasattr(location, attr):
            location = getattr(location, attr)
        else:
            break
    return location


def is_method(method: MethodOrProperty) -> bool:
    """Return if the function is method/property declared in a class"""
    return (isinstance(method, property) and is_method(method.fget)) or (
        isinstance(method, FunctionType)
        and method.__name__ != method.__qualname__
        and isinstance(_method_location(method), (type, type(None)))
        and next(iter(signature(method).parameters), None) == "self"
    )


def method_class(method: MethodOrProperty) -> Optional[Type]:
    cls = _method_location(method)
    return cls if isinstance(cls, type) else None


METHOD_WRAPPER_ATTR = f"{PREFIX}method_wrapper"


def method_wrapper(method: MethodOrProperty, name: str = None) -> Callable:
    if isinstance(method, property):
        name = name or method.fget.__name__

        @wraps(method.fget)
        def wrapper(self):
            return getattr(self, name)

    else:
        if hasattr(method, METHOD_WRAPPER_ATTR):
            return method
        name = name or method.__name__

        @wraps(method)
        def wrapper(self, *args, **kwargs):
            return getattr(self, name)(*args, **kwargs)

    setattr(wrapper, METHOD_WRAPPER_ATTR, True)
    return wrapper


class MethodWrapper(Generic[T]):
    def __init__(self, method: T):
        self._method = method

    def getter(self, func):
        self._method.getter(func)
        return self

    def setter(self, func):
        self._method.setter(func)
        return self

    def deleter(self, func):
        self._method.deleter(func)
        return self

    def __set_name__(self, owner, name):
        setattr(owner, name, self._method)

    def __call__(self, *args, **kwargs):
        raise RuntimeError("Method __set_name__ has not been called")


def method_registerer(
    arg: Optional[Callable],
    owner: Optional[Type],
    register: Callable[[Callable, Optional[Type], str], None],
):
    def decorator(method: MethodOrProperty):
        if owner is None and is_method(method) and method_class(method) is None:

            class ResolverDescriptor(MethodWrapper[MethodOrProperty]):
                def __set_name__(self, owner, name):
                    super().__set_name__(owner, name)
                    register(method_wrapper(method), owner, name)

            return ResolverDescriptor(method)
        else:
            owner2 = owner
            if is_method(method):
                if owner2 is None:
                    owner2 = method_class(method)
                method = method_wrapper(method)
            assert not isinstance(method, property)
            register(cast(Callable, method), owner2, method.__name__)
            return method

    return decorator if arg is None else decorator(arg)


def replace_builtins(tp: AnyType) -> AnyType:
    origin = get_origin_or_type(tp)
    args = tuple(map(replace_builtins, get_args2(tp)))
    if origin in COLLECTION_TYPES:
        if issubclass(origin, collections.abc.Set):
            replacement = subscriptable_origin(Set[None])
        else:
            replacement = subscriptable_origin(List[None])
    elif origin in MAPPING_TYPES:
        replacement = subscriptable_origin(Dict[None, None])
    else:
        replacement = origin
    res = replacement[args] if args else replacement
    return Annotated[(res, *get_args(tp)[1:])] if get_origin(tp) == Annotated else res


def sort_by_annotations_position(
    cls: Type, elts: Collection[T], key: Callable[[T], str]
) -> List[T]:
    annotations: Dict[str, Any] = OrderedDict()
    for base in reversed(cls.__mro__):
        annotations.update(getattr(base, "__annotations__", ()))
    positions = {key: i for i, key in enumerate(annotations)}
    return sorted(elts, key=lambda elt: positions.get(key(elt), len(positions)))


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
