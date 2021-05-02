from dataclasses import dataclass
from typing import Dict, Optional, TypeVar

from apischema.objects.conversions import ObjectWrapper
from apischema.types import AnyType, PRIMITIVE_TYPES
from apischema.utils import (
    contains,
    get_origin_or_type,
    has_type_vars,
    is_type_var,
    replace_builtins,
)

_refs: Dict[AnyType, Optional[str]] = {}


def _default_ref(tp: AnyType) -> Optional[str]:
    if (
        hasattr(tp, "__name__")
        and not getattr(tp, "__parameters__", ())
        and not contains(PRIMITIVE_TYPES, tp)
    ):
        return tp.__name__
    origin = get_origin_or_type(tp)
    if isinstance(origin, type) and issubclass(origin, ObjectWrapper):
        return origin.type.__name__
    return None


def get_ref(tp: AnyType) -> Optional[str]:
    tp = replace_builtins(tp)
    return _refs[tp] if contains(_refs, tp) else _default_ref(tp)


def check_ref_type(tp: AnyType):
    if is_type_var(tp):
        raise TypeError("TypeVar cannot have a ref")
    elif has_type_vars(tp):
        raise TypeError("Unspecialized generic types cannot have a ref")


T = TypeVar("T")


@dataclass(frozen=True)
class schema_ref:
    ref: Optional[str]

    def __post_init__(self):
        if self.ref == "":
            raise ValueError("Empty schema ref not allowed")

    def check_type(self, tp: AnyType):
        if is_type_var(tp):
            raise TypeError("TypeVar cannot have a ref")
        elif has_type_vars(tp):
            raise TypeError("Unspecialized generic types cannot have a ref")

    def __call__(self, tp: T) -> T:
        check_ref_type(tp)
        _refs[replace_builtins(tp)] = self.ref
        return tp
