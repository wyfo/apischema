import collections.abc
import inspect
import re
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from types import MappingProxyType
from typing import (
    AbstractSet,
    Any,
    Awaitable,
    Callable,
    Collection,
    Container,
    Generic,
    Iterable,
    Mapping,
    NoReturn,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.types import COLLECTION_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES, AnyType
from apischema.typing import (
    _collect_type_parameters,
    generic_mro,
    get_args,
    get_origin,
    get_type_hints,
    is_annotated,
    is_type_var,
    is_union,
    typing_origin,
)

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

PREFIX = "_apischema_"

T = TypeVar("T")
U = TypeVar("U")


def identity(x: T) -> T:
    return x


Lazy = Callable[[], T]


@dataclass(frozen=True)  # dataclass enable equality check
class LazyValue(Generic[T]):
    default: T

    def __call__(self) -> T:
        return self.default


def is_hashable(obj: Any) -> bool:
    return isinstance(obj, collections.abc.Hashable)


def opt_or(opt: Optional[T], default: U) -> Union[T, U]:
    return opt if opt is not None else default


SNAKE_CASE_REGEX = re.compile(r"_([a-z\d])")
CAMEL_CASE_REGEX = re.compile(r"([a-z\d])([A-Z])")


def to_camel_case(s: str) -> str:
    return SNAKE_CASE_REGEX.sub(lambda m: m.group(1).upper(), s)


def to_snake_case(s: str) -> str:
    return CAMEL_CASE_REGEX.sub(lambda m: m.group(1) + "_" + m.group(2).lower(), s)


def to_pascal_case(s: str) -> str:
    camel = to_camel_case(s)
    return camel[0].upper() + camel[1:] if camel else camel


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


def has_type_vars(tp: AnyType) -> bool:
    return is_type_var(tp) or bool(getattr(tp, "__parameters__", ()))


TV = AnyType  # TypeVar is not supported as a type
# 10 should be enough for all builtin types
_type_vars = [TypeVar(f"T{i}") for i in range(10)]


def get_parameters(tp: AnyType) -> Iterable[TV]:
    if hasattr(tp, "__parameters__"):
        return tp.__parameters__
    elif hasattr(tp, "__orig_bases__"):
        return _collect_type_parameters(tp.__orig_bases__)
    elif is_type_var(tp):
        return (tp,)
    else:
        return _type_vars


def substitute_type_vars(tp: AnyType, substitution: Mapping[TV, AnyType]) -> AnyType:
    if is_type_var(tp):
        try:
            return substitution[tp]
        except KeyError:
            return Union[tp.__constraints__] if tp.__constraints__ else Any
    elif getattr(tp, "__parameters__", ()):
        return (Union if is_union(tp) else tp)[
            tuple(substitution.get(p, p) for p in tp.__parameters__)
        ]
    else:
        return tp


Func = TypeVar("Func", bound=Callable)


def typed_wraps(wrapped: Func) -> Callable[[Callable], Func]:
    return cast(Func, wraps(wrapped))


def is_subclass(tp: AnyType, base: AnyType) -> bool:
    tp, base = get_origin_or_type(tp), get_origin_or_type(base)
    return tp == base or (
        isinstance(tp, type) and isinstance(base, type) and issubclass(tp, base)
    )


def no_annotated(tp: AnyType) -> AnyType:
    return get_args(tp)[0] if is_annotated(tp) else tp


def get_origin_or_type(tp: AnyType) -> AnyType:
    origin = get_origin(tp)
    return origin if origin is not None else tp


def get_origin2(tp: AnyType) -> Optional[Type]:
    return get_origin(no_annotated(tp))  # type: ignore


def get_args2(tp: AnyType) -> Tuple[AnyType, ...]:
    return get_args(no_annotated(tp))


def get_origin_or_type2(tp: AnyType) -> AnyType:
    tp2 = no_annotated(tp)
    origin = get_origin(tp2)
    return origin if origin is not None else tp2


def keep_annotations(tp: AnyType, annotated: AnyType) -> AnyType:
    return Annotated[(tp, *get_args(annotated)[1:])] if is_annotated(annotated) else tp


def with_parameters(tp: AnyType) -> AnyType:
    return tp[tp.__parameters__] if getattr(tp, "__parameters__", ()) else tp


def is_union_of(tp: AnyType, of: AnyType) -> bool:
    return tp == of or (is_union(get_origin_or_type2(tp)) and of in get_args2(tp))


LIST_ORIGIN = typing_origin(list)
SET_ORIGIN = typing_origin(set)
TUPLE_ORIGIN = typing_origin(tuple)
DICT_ORIGIN = typing_origin(dict)


def replace_builtins(tp: AnyType) -> AnyType:
    origin = get_origin2(tp)
    if origin is None:
        return tp
    args = tuple(map(replace_builtins, get_args2(tp)))
    replacement: Any
    if origin in COLLECTION_TYPES:
        if issubclass(origin, collections.abc.Set):
            replacement = SET_ORIGIN
        elif not issubclass(origin, tuple):
            replacement = LIST_ORIGIN
        elif len(args) == 2 and args[1] is ...:
            args = args[:1]
            replacement = LIST_ORIGIN
        else:
            replacement = TUPLE_ORIGIN
    elif origin in MAPPING_TYPES:
        replacement = DICT_ORIGIN
    elif is_union(origin):
        replacement = Union
    else:
        replacement = typing_origin(origin)
    res = replacement[args] if args else replacement
    return keep_annotations(res, tp)


def stop_signature_abuse() -> NoReturn:
    raise TypeError("Stop signature abuse")


empty_dict: Mapping[str, Any] = MappingProxyType({})

ITERABLE_TYPES = {
    *COLLECTION_TYPES,
    *MAPPING_TYPES,
    Iterable,
    collections.abc.Iterable,
    Container,
    collections.abc.Container,
}


def subtyping_substitution(
    supertype: AnyType, subtype: AnyType
) -> Tuple[Mapping[AnyType, AnyType], Mapping[AnyType, AnyType]]:
    if not get_args(subtype) and not isinstance(subtype, type):
        return {}, {}
    supertype, subtype = with_parameters(supertype), with_parameters(subtype)
    supertype_to_subtype, subtype_to_supertype = {}, {}
    super_origin = get_origin_or_type2(supertype)
    for base in generic_mro(subtype):
        base_origin = get_origin_or_type2(base)
        if base_origin == super_origin or (
            base_origin in ITERABLE_TYPES and super_origin in ITERABLE_TYPES
        ):
            for base_arg, super_arg in zip(get_args2(base), get_args2(supertype)):
                if is_type_var(super_arg):
                    supertype_to_subtype[super_arg] = base_arg
                if is_type_var(base_arg):
                    subtype_to_supertype[base_arg] = super_arg
            break
    return supertype_to_subtype, subtype_to_supertype


def literal_values(values: Sequence[Any]) -> Sequence[Any]:
    primitive_values = [v.value if isinstance(v, Enum) else v for v in values]
    if any(not isinstance(v, PRIMITIVE_TYPES) for v in primitive_values):
        raise TypeError("Only primitive types are supported for Literal/Enum")
    return primitive_values


awaitable_origin = get_origin(Awaitable[Any])


def is_async(func: Callable, types: Optional[Mapping[str, AnyType]] = None) -> bool:
    wrapped_func = func
    while hasattr(wrapped_func, "__wrapped__"):
        wrapped_func = wrapped_func.__wrapped__
    if inspect.iscoroutinefunction(wrapped_func):
        return True
    if types is None:
        try:
            types = get_type_hints(func)
        except Exception:
            types = {}
    return get_origin_or_type2(types.get("return")) == awaitable_origin


@contextmanager
def context_setter(obj: Any):
    dict_copy = obj.__dict__.copy()
    try:
        yield
    finally:
        obj.__dict__.clear()
        obj.__dict__.update(dict_copy)


CollectionOrPredicate = Union[Collection[T], Callable[[T], bool]]


def as_predicate(
    collection_or_predicate: CollectionOrPredicate[T],
) -> Callable[[T], bool]:
    if not isinstance(collection_or_predicate, Collection):
        return collection_or_predicate
    elif not collection_or_predicate:
        return lambda _: False
    collection = collection_or_predicate
    if not isinstance(collection, AbstractSet):
        with suppress(Exception):
            collection = set(collection)

    def wrapper(elt: T) -> bool:
        try:
            return elt in collection
        except Exception:
            return False

    return wrapper
