import collections.abc
import warnings
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, MutableMapping, NamedTuple, Optional, TypeVar, Union

from apischema.cache import CacheAwareDict
from apischema.types import PRIMITIVE_TYPES, AnyType
from apischema.typing import (
    get_args,
    get_origin,
    is_named_tuple,
    is_type_var,
    is_typed_dict,
)
from apischema.utils import has_type_vars, merge_opts, replace_builtins


class TypeName(NamedTuple):
    json_schema: Optional[str] = None
    graphql: Optional[str] = None


NameOrFactory = Union[str, None, Callable[..., Optional[str]]]


def _apply_args(name_or_factory: NameOrFactory, *args) -> Optional[str]:
    return name_or_factory(*args) if callable(name_or_factory) else name_or_factory


_type_names: MutableMapping[AnyType, "TypeNameFactory"] = CacheAwareDict({})

T = TypeVar("T")


@dataclass(frozen=True)
class TypeNameFactory:
    json_schema: NameOrFactory
    graphql: NameOrFactory

    def __call__(self, tp: T) -> T:
        self.check_type(tp)
        _type_names[replace_builtins(tp)] = self
        return tp

    def check_type(self, tp: AnyType):
        if is_type_var(tp):
            raise TypeError("TypeVar cannot have a type_name")
        if has_type_vars(tp):
            if get_args(tp):
                raise TypeError("Generic alias cannot have a type_name")
            elif isinstance(self.json_schema, str) or isinstance(self.graphql, str):
                raise TypeError(
                    "Unspecialized generic type must used factory type_name"
                )

    def to_type_name(self, tp: AnyType, *args) -> TypeName:
        self.check_type(tp)
        return TypeName(
            _apply_args(self.json_schema, tp, *args),
            _apply_args(self.graphql, tp, *args),
        )


def type_name(
    ref: NameOrFactory = None,
    *,
    json_schema: NameOrFactory = None,
    graphql: NameOrFactory = None,
) -> TypeNameFactory:
    return TypeNameFactory(json_schema or ref, graphql or ref)


no_type_name = {*PRIMITIVE_TYPES, Any}


def default_type_name(tp: AnyType) -> Optional[TypeName]:
    if (
        hasattr(tp, "__name__")
        and not get_args(tp)
        and not has_type_vars(tp)
        and tp not in no_type_name
        and (
            not isinstance(tp, type)
            or not issubclass(tp, collections.abc.Collection)
            or is_named_tuple(tp)
            or is_typed_dict(tp)
        )
    ):
        return TypeName(tp.__name__, tp.__name__)
    else:
        return None


def get_type_name(tp: AnyType) -> TypeName:
    from apischema import settings

    tp = replace_builtins(tp)
    with suppress(KeyError, TypeError):
        return _type_names[tp].to_type_name(tp)
    origin, args = get_origin(tp), get_args(tp)
    if args and not has_type_vars(tp):
        with suppress(KeyError, TypeError):
            return _type_names[origin].to_type_name(origin, *args)
    return settings.default_type_name(tp) or TypeName()


@merge_opts
def merge_type_name(default: TypeName, override: TypeName) -> TypeName:
    return TypeName(
        override.json_schema or default.json_schema, override.graphql or default.graphql
    )


def schema_ref(ref: Optional[str]) -> Callable[[T], T]:
    warnings.warn("schema_ref is deprecated, use type_name instead", DeprecationWarning)
    return type_name(ref)
