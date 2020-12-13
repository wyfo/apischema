from contextlib import suppress
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

from apischema.dataclass_utils import is_dataclass
from apischema.types import AnyType
from apischema.typing import _TypedDictMeta, get_origin
from apischema.utils import is_type_var, type_name
from apischema.visitor import Unsupported, Visitor

Ref = Union[str, "ellipsis", None]  # noqa: F821
_refs: Dict[AnyType, Optional[Ref]] = {}


def _default_ref(cls: AnyType) -> Ref:
    if not hasattr(cls, "__parameters__") and (
        (isinstance(cls, type) and is_dataclass(cls))
        or (hasattr(cls, "__supertype__") and is_builtin(cls))
        or isinstance(cls, _TypedDictMeta)
    ):
        return ...
    else:
        with suppress(TypeError):
            if (issubclass(cls, tuple) and hasattr(cls, "_field")) or issubclass(
                cls, Enum
            ):
                return ...
        return None


def get_ref(cls: AnyType) -> Optional[str]:
    ref = _refs[cls] if cls in _refs else _default_ref(cls)
    return cast(Optional[str], type_name(cls) if ref is ... else ref)


T = TypeVar("T")


@dataclass(frozen=True)
class schema_ref:
    ref: Ref = ...

    def __post_init__(self):
        if self.ref == "":
            raise ValueError("Empty schema ref not allowed")

    def check_type(self, cls: AnyType):
        if hasattr(cls, "__supertype__") and not is_builtin(cls):
            # NewType of non-builtin types cannot have a ref because their serialization
            # could be customized, but the NewType ref would then erase this
            # customization in the schema.
            raise TypeError("NewType of non-builtin type can not have a ref")
        if is_type_var(cls):
            raise TypeError("TypeVar cannot have a ref")
        elif getattr(cls, "__parameters__", ()):
            raise TypeError("Unspecialized generic types cannot have a ref")
        if get_origin(cls) is not None and self.ref is ...:
            raise TypeError(f"Generic alias {cls} cannot have ... ref")

    def __call__(self, cls: T) -> T:
        self.check_type(cls)
        _refs[cls] = self.ref
        return cls


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
        raise NotImplementedError()

    def union(self, alternatives: Sequence[AnyType]):
        for alt in alternatives:
            self.visit(alt)


def is_builtin(cls: AnyType) -> bool:
    try:
        BuiltinVisitor().visit(cls)
    except (NotImplementedError, Unsupported):
        return False
    else:
        return True
