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

from apischema.dataclasses import is_dataclass
from apischema.json_schema.annotations import get_annotations
from apischema.json_schema.constraints import get_constraints
from apischema.types import AnyType
from apischema.typing import _TypedDictMeta
from apischema.utils import type_name
from apischema.visitor import Visitor

Ref = Union[str, "ellipsis", None]  # noqa: F821
_refs: Dict[AnyType, Optional[Ref]] = {}


def _default_ref(cls: AnyType) -> Ref:
    if (
        is_dataclass(cls)
        or hasattr(cls, "__supertype__")
        or isinstance(cls, _TypedDictMeta)
        or get_annotations(cls) is not None
        or get_constraints(cls) is not None
    ):
        return ...
    else:
        with suppress(TypeError):
            if issubclass(cls, tuple) and hasattr(cls, "_field"):
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
        """Check if the given type can have a ref

        NewType of non-builtin types cannot have a ref because their serialization
        could be customized, but the NewType ref would then erase this customization
        in the schema"""
        if hasattr(cls, "__supertype__") and not is_builtin(cls):
            raise TypeError("NewType of non-builtin type can not have a ref")

    def __call__(self, cls: T) -> T:
        self.check_type(cls)
        _refs[cls] = self.ref
        return cls


class BuiltinVisitor(Visitor):
    def collection(self, cls: Type[Iterable], value_type: AnyType, _):
        self.visit(value_type, _)

    def enum(self, cls: Type[Enum], _):
        pass

    def literal(self, values: Sequence[Any], _):
        pass

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType, _):
        self.visit(key_type, _), self.visit(value_type, _)

    def primitive(self, cls: Type, _):
        pass

    def subprimitive(self, cls: Type, superclass: Type, _):
        raise NotImplementedError()

    def union(self, alternatives: Sequence[AnyType], _):
        for alt in alternatives:
            self.visit(alt, _)

    def unsupported(self, cls: Type, _):
        raise NotImplementedError()


def is_builtin(cls: AnyType) -> bool:
    try:
        BuiltinVisitor().visit(cls, ...)
    except NotImplementedError:
        return False
    else:
        return True
