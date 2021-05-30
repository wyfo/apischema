import collections.abc
import inspect
import re
import sys
from dataclasses import is_dataclass
from functools import wraps
from types import FunctionType
from typing import (
    Any,
    Awaitable,
    Callable,
    Collection,
    Container,
    Dict,
    Generic,
    Hashable,
    Iterable,
    List,
    Mapping,
    NoReturn,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.types import AnyType, COLLECTION_TYPES, MAPPING_TYPES, OrderedDict
from apischema.typing import (
    _collect_type_vars,
    generic_mro,
    get_args,
    get_origin,
    get_type_hints,
    is_annotated,
)

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

PREFIX = "_apischema_"

T = TypeVar("T")
U = TypeVar("U")


if sys.version_info <= (3, 7):  # pragma: no cover
    is_dataclass_ = is_dataclass

    def is_dataclass(obj) -> bool:
        return is_dataclass_(obj) and getattr(obj, "__origin__", None) is None


def opt_or(opt: Optional[T], default: U) -> Union[T, U]:
    return opt if opt is not None else default


def to_hashable(data: Union[None, int, float, str, bool, list, dict]) -> Hashable:
    if isinstance(data, list):
        return tuple(map(to_hashable, data))
    if isinstance(data, dict):
        return tuple(sorted((to_hashable(k), to_hashable(v)) for k, v in data.items()))
    return data  # type: ignore


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


def _annotated(tp: AnyType) -> AnyType:
    return get_args(tp)[0] if is_annotated(tp) else tp


def get_origin_or_type(tp: AnyType) -> AnyType:
    origin = get_origin(tp)
    return origin if origin is not None else tp


def get_origin2(tp: AnyType) -> Optional[Type]:
    return get_origin(_annotated(tp))


def get_args2(tp: AnyType) -> Tuple[AnyType, ...]:
    return get_args(_annotated(tp))


def get_origin_or_type2(tp: AnyType) -> AnyType:
    tp2 = _annotated(tp)
    origin = get_origin(tp2)
    return origin if origin is not None else tp2


def keep_annotations(tp: AnyType, annotated: AnyType) -> AnyType:
    return Annotated[(tp, *get_args(annotated)[1:])] if is_annotated(annotated) else tp


def with_parameters(tp: AnyType) -> AnyType:
    return tp[tp.__parameters__] if getattr(tp, "__parameters__", ()) else tp


def is_union_of(tp: AnyType, of: AnyType) -> bool:
    return tp == of or (get_origin_or_type2(tp) == Union and of in get_args2(tp))


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
        and next(iter(inspect.signature(method).parameters), None) == "self"
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
    register: Callable[[Callable, Type, str], None],
):
    def decorator(method: MethodOrProperty):
        if owner is None and is_method(method) and method_class(method) is None:

            class Descriptor(MethodWrapper[MethodOrProperty]):
                def __set_name__(self, owner, name):
                    super().__set_name__(owner, name)
                    register(method_wrapper(method), owner, name)

            return Descriptor(method)
        else:
            owner2 = owner
            if is_method(method):
                if owner2 is None:
                    owner2 = method_class(method)
                method = method_wrapper(method)
            if owner2 is None:
                try:
                    hints = get_type_hints(method)
                    owner2 = get_origin_or_type2(hints[next(iter(hints))])
                except (KeyError, StopIteration):
                    raise TypeError("First parameter of method must be typed") from None
            assert not isinstance(method, property)
            register(cast(Callable, method), owner2, method.__name__)
            return method

    return decorator if arg is None else decorator(arg)


def replace_builtins(tp: AnyType) -> AnyType:
    origin = get_origin2(tp)
    if origin is None:
        return tp
    args = tuple(map(replace_builtins, get_args2(tp)))
    replacement: Any
    if origin in COLLECTION_TYPES:
        if issubclass(origin, collections.abc.Set):
            replacement = Set
        else:
            replacement = List
    elif origin in MAPPING_TYPES:
        replacement = Dict
    else:
        replacement = origin
    res = replacement[args] if args else replacement
    return keep_annotations(res, tp)


def sort_by_annotations_position(
    cls: Type, elts: Collection[T], key: Callable[[T], str]
) -> List[T]:
    annotations: Dict[str, Any] = OrderedDict()
    for base in reversed(cls.__mro__):
        annotations.update(getattr(base, "__annotations__", ()))
    positions = {key: i for i, key in enumerate(annotations)}
    return sorted(elts, key=lambda elt: positions.get(key(elt), len(positions)))


def stop_signature_abuse() -> NoReturn:
    raise TypeError("Stop signature abuse")


empty_dict: Mapping[str, Any] = {}
ITERABLE_TYPES = (
    COLLECTION_TYPES.keys()
    | MAPPING_TYPES.keys()
    | {Iterable, collections.abc.Iterable, Container, collections.abc.Container}
)


def subtyping_substitution(
    supertype: AnyType, subtype: AnyType
) -> Tuple[Mapping[AnyType, AnyType], Mapping[AnyType, AnyType]]:
    supertype, subtype = with_parameters(supertype), with_parameters(subtype)
    supertype_to_subtype, subtype_to_supertype = {}, {}
    super_origin = get_origin_or_type2(supertype)
    for base in generic_mro(subtype):
        base_origin = get_origin_or_type2(base)
        if base_origin == super_origin or (
            base_origin in ITERABLE_TYPES and super_origin in ITERABLE_TYPES
        ):
            for base_arg, super_arg in zip(get_args(base), get_args(supertype)):
                if is_type_var(super_arg):
                    supertype_to_subtype[super_arg] = base_arg
                if is_type_var(base_arg):
                    subtype_to_supertype[base_arg] = super_arg
            break
    return supertype_to_subtype, subtype_to_supertype


awaitable_origin = get_origin(Awaitable[Any])


def is_async(func: Callable, types: Mapping[str, AnyType] = None) -> bool:
    wrapped_func = func
    while hasattr(wrapped_func, "__wrapped__"):
        wrapped_func = wrapped_func.__wrapped__  # type: ignore
    if inspect.iscoroutinefunction(wrapped_func):
        return True
    if types is None:
        try:
            types = get_type_hints(func)
        except Exception:
            types = {}
    return get_origin_or_type2(types.get("return")) == awaitable_origin


def wrap_generic_init_subclass(init_subclass: Func) -> Func:
    if sys.version_info >= (3, 7):
        return init_subclass

    @wraps(init_subclass)
    def wrapper(cls, **kwargs):
        return init_subclass(cls, **kwargs) if cls.__origin__ is None else None

    return wrapper
