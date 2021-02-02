from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.conversions.visitor import SELF_CONVERSION_ATTR
from apischema.dataclass_utils import is_dataclass
from apischema.types import AnyType
from apischema.typing import _GenericAlias, _TypedDictMeta, get_origin
from apischema.utils import contains, has_type_vars, is_type_var, replace_builtins
from apischema.visitor import Unsupported, Visitor

Ref = Union[str, "ellipsis", None]  # noqa: F821
_refs: Dict[AnyType, Optional[Ref]] = {}


def _default_ref(tp: AnyType) -> Ref:
    if (
        not has_type_vars(tp)
        and not hasattr(tp, SELF_CONVERSION_ATTR)
        and (
            (
                isinstance(tp, type)
                and (
                    is_dataclass(tp)
                    or (issubclass(tp, tuple) and hasattr(tp, "_fields"))
                    or issubclass(tp, Enum)
                )
            )
            or (hasattr(tp, "__supertype__") and is_builtin(tp))
            or isinstance(tp, _TypedDictMeta)
        )
    ):
        return ...
    else:
        return None


def get_ref(tp: AnyType) -> Optional[str]:
    tp = replace_builtins(tp)
    ref = _refs[tp] if contains(_refs, tp) else _default_ref(tp)
    if ref is not ...:
        return cast(Optional[str], ref)
    elif hasattr(tp, "__name__"):
        return tp.__name__
    elif isinstance(tp, _GenericAlias):
        return tp._name
    else:
        return None


T = TypeVar("T")


@dataclass(frozen=True)
class schema_ref:
    ref: Ref = ...

    def __post_init__(self):
        if self.ref == "":
            raise ValueError("Empty schema ref not allowed")

    def check_type(self, tp: AnyType):
        if hasattr(tp, "__supertype__") and not is_builtin(tp):
            # NewType of non-builtin types cannot have a ref because their serialization
            # could be customized, but the NewType ref would then erase this
            # customization in the schema.
            raise TypeError("NewType of non-builtin type can not have a ref")
        if is_type_var(tp):
            raise TypeError("TypeVar cannot have a ref")
        elif has_type_vars(tp):
            raise TypeError("Unspecialized generic types cannot have a ref")
        if get_origin(tp) is not None and self.ref is ...:
            raise TypeError(f"Generic alias {tp} cannot have ... ref")

    def __call__(self, tp: T) -> T:
        self.check_type(tp)
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
