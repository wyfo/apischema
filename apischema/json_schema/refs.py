from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Type, TypeVar

from apischema.conversions.visitor import SELF_CONVERSION_ATTR
from apischema.dataclass_utils import is_dataclass
from apischema.types import AnyType
from apischema.typing import _TypedDictMeta
from apischema.utils import contains, has_type_vars, is_type_var, replace_builtins
from apischema.visitor import Unsupported, Visitor

_refs: Dict[AnyType, Optional[str]] = {}


def _default_ref(tp: AnyType) -> Optional[str]:
    if (
        isinstance(tp, type)
        and not getattr(tp, "__parameters__", ())
        and not hasattr(tp, SELF_CONVERSION_ATTR)
        and (
            is_dataclass(tp)
            or (issubclass(tp, tuple) and hasattr(tp, "_fields"))
            or issubclass(tp, Enum)
            or isinstance(tp, _TypedDictMeta)
        )
    ) or hasattr(tp, "__supertype__"):
        return tp.__name__
    else:
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


class BuiltinVisitor(Visitor):
    def collection(self, cls: Type[Iterable], value_type: AnyType):
        self.visit(value_type)

    def enum(self, cls: Type[Enum]):
        pass

    def literal(self, values: Sequence[Any]):
        pass

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType):
        self.visit(key_type), self.visit(value_type)

    def primitive(self, cls: Type):
        pass

    def subprimitive(self, cls: Type, superclass: Type):
        raise NotImplementedError

    def union(self, alternatives: Sequence[AnyType]):
        for alt in alternatives:
            self.visit(alt)


def is_builtin(tp: AnyType) -> bool:
    try:
        BuiltinVisitor().visit(tp)
    except (NotImplementedError, Unsupported):
        return False
    else:
        return True
