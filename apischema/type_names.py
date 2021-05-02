import warnings
from dataclasses import dataclass
from typing import Callable, Dict, Optional, TypeVar

from apischema.types import AnyType, PRIMITIVE_TYPES
from apischema.typing import get_args
from apischema.utils import contains, has_type_vars, is_type_var, replace_builtins

_type_names: Dict[AnyType, "TypeName"] = {}

T = TypeVar("T")


@dataclass
class TypeName:
    json_schema: Optional[str]
    graphql: Optional[str]

    def __call__(self, tp: T) -> T:
        check_type_with_name(tp)
        _type_names[replace_builtins(tp)] = self
        return tp


def _default_type_name(tp: AnyType) -> TypeName:
    if (
        hasattr(tp, "__name__")
        and not get_args(tp)
        and not has_type_vars(tp)
        and tp not in PRIMITIVE_TYPES
    ):
        return TypeName(tp.__name__, tp.__name__)
    else:
        return TypeName(None, None)


def get_type_name(tp: AnyType) -> TypeName:
    tp = replace_builtins(tp)
    return _type_names[tp] if contains(_type_names, tp) else _default_type_name(tp)


def check_type_with_name(tp: AnyType):
    if is_type_var(tp):
        raise TypeError("TypeVar cannot have a ref")
    elif has_type_vars(tp):
        raise TypeError("Unspecialized generic types cannot have a ref")


def type_name(
    ref: Optional[str] = None,
    *,
    json_schema: Optional[str] = None,
    graphql: Optional[str] = None
) -> Callable[[T], T]:
    return TypeName(json_schema or ref, graphql or ref)


def schema_ref(ref: Optional[str]) -> Callable[[T], T]:
    warnings.warn("schema_ref is deprecated, use type_name instead", DeprecationWarning)
    return type_name(ref)
