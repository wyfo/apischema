from dataclasses import Field, is_dataclass
from enum import Enum
from functools import lru_cache
from types import MappingProxyType
from typing import (
    Any,
    Collection,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.dataclass_utils import dataclass_types_and_fields
from apischema.type_vars import TypeVarContext, resolve_type_vars, type_var_context
from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    OrderedDict,
    PRIMITIVE_TYPES,
)
from apischema.typing import (
    _LiteralMeta,
    _TypedDictMeta,
    get_args,
    get_origin,
    get_type_hints,
)
from apischema.utils import is_type_var

try:
    from apischema.typing import Annotated, Literal
except ImportError:
    Annotated, Literal = ..., ...  # type: ignore

TUPLE_TYPE = get_origin(Tuple[Any])


@lru_cache()
def type_hints_cache(obj) -> Mapping[str, AnyType]:
    # Use immutable return because of cache
    return MappingProxyType(get_type_hints(obj, include_extras=True))


class Unsupported(TypeError):
    def __init__(self, cls: Type):
        self.cls = cls


Return = TypeVar("Return", covariant=True)


class Visitor(Generic[Return]):
    def __init__(self):
        self._type_vars: Optional[TypeVarContext] = None

    def _resolve_type_vars(self, cls: AnyType) -> Any:
        return resolve_type_vars(cls, self._type_vars)

    def annotated(self, cls: AnyType, annotations: Sequence[Any]) -> Return:
        return self.visit(cls)

    def any(self) -> Return:
        raise NotImplementedError()

    def collection(self, cls: Type[Collection], value_type: AnyType) -> Return:
        raise NotImplementedError()

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Return:
        raise NotImplementedError()

    def enum(self, cls: Type[Enum]) -> Return:
        raise NotImplementedError()

    def generic(self, cls: AnyType) -> Return:
        type_vars = self._type_vars
        try:
            self._type_vars = type_var_context(cls, self._type_vars)
            return self._visit(get_origin(cls))
        finally:
            self._type_vars = type_vars

    def literal(self, values: Sequence[Any]) -> Return:
        raise NotImplementedError()

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Return:
        raise NotImplementedError()

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> Return:
        raise NotImplementedError()

    def new_type(self, cls: AnyType, super_type: AnyType) -> Return:
        return self.visit(super_type)

    def primitive(self, cls: Type) -> Return:
        raise NotImplementedError()

    def subprimitive(self, cls: Type, superclass: Type) -> Return:
        return self.primitive(superclass)

    def tuple(self, types: Sequence[AnyType]) -> Return:
        raise NotImplementedError()

    def typed_dict(self, cls: Type, keys: Mapping[str, AnyType], total: bool) -> Return:
        raise NotImplementedError()

    def _union_result(self, results: Iterable[Return]) -> Return:
        raise NotImplementedError()

    def union(self, alternatives: Sequence[AnyType]) -> Return:
        return self._union_result(map(self.visit, alternatives))

    def unsupported(self, cls: AnyType) -> Return:
        raise Unsupported(cls) from None

    def _visit_generic(self, cls: AnyType) -> Return:
        origin, args = get_origin(cls), get_args(cls)
        assert origin is not None
        if origin is Annotated:
            return self.annotated(args[0], args[1:])
        if origin is Union:
            return self.union(args)
        if origin is TUPLE_TYPE:
            if len(args) < 2 or args[1] is not ...:
                return self.tuple(args)
        if origin in COLLECTION_TYPES:
            return self.collection(origin, args[0])
        if origin in MAPPING_TYPES:
            return self.mapping(origin, args[0], args[1])
        if origin is Literal:  # pragma: no cover py37+
            return self.literal(args)
        return self.generic(cls)

    def _visit(self, cls: AnyType) -> Return:
        if cls in PRIMITIVE_TYPES:
            return self.primitive(cls)
        if is_dataclass(cls):
            return self.dataclass(cls, *dataclass_types_and_fields(cls))  # type: ignore
        if hasattr(cls, "__supertype__"):
            return self.new_type(cls, cls.__supertype__)
        if cls is Any:
            return self.any()
        if cls in COLLECTION_TYPES:
            return self.collection(cls, Any)
        if cls in MAPPING_TYPES:
            return self.mapping(cls, Any, Any)
        try:
            issubclass(cls, object)
        except TypeError:
            pass
        else:
            if issubclass(cls, Enum):
                return self.enum(cls)
            for primitive in PRIMITIVE_TYPES:
                if issubclass(cls, primitive):
                    return self.subprimitive(cls, primitive)
            # NamedTuple
            if issubclass(cls, tuple) and hasattr(cls, "_fields"):
                if hasattr(cls, "__annotations__"):
                    types = type_hints_cache(cls)
                elif hasattr(cls, "__field_types"):  # pragma: no cover
                    types = cls._field_types  # type: ignore
                else:  # pragma: no cover
                    types = OrderedDict((f, Any) for f in cls._fields)  # type: ignore
                return self.named_tuple(cls, types, cls._field_defaults)  # type: ignore
        if isinstance(cls, _LiteralMeta):  # pragma: no cover py36
            return self.literal(cls.__values__)  # type: ignore
        # cannot use issubclass(..., TypedDict)
        if isinstance(cls, _TypedDictMeta):
            total = cls.__total__  # type: ignore
            assert isinstance(cls, type)
            return self.typed_dict(cls, type_hints_cache(cls), total)
        return self.unsupported(cls)

    def visit(self, cls: AnyType) -> Return:
        if get_origin(cls) is not None:
            return self._visit_generic(cls)
        if is_type_var(cls):
            return self.visit(self._resolve_type_vars(cls))
        else:
            type_vars = self._type_vars
            self._type_vars = None
            try:
                return self._visit(cls)
            finally:
                self._type_vars = type_vars
