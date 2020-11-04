from dataclasses import Field, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import (
    Any,
    Collection,
    Generic,
    Iterable,
    Mapping,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.dataclass_utils import get_all_fields, resolve_dataclass_types
from apischema.type_vars import TypeVarResolver
from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    OrderedDict,
    PRIMITIVE_TYPES,
    TUPLE_TYPE,
)
from apischema.typing import (
    _LiteralMeta,
    _TypedDictMeta,
    get_args,
    get_origin,
    get_type_hints,
)

try:
    from apischema.typing import Annotated, Literal
except ImportError:
    Annotated, Literal = ..., ...  # type: ignore


@lru_cache()
def type_hints_cache(obj):
    return get_type_hints(obj, include_extras=True)


@lru_cache()
def dataclass_types_and_fields(
    cls: Type,
) -> Tuple[Mapping[str, AnyType], Sequence[Field], Sequence[Field]]:
    assert is_dataclass(cls)
    types, init_only = resolve_dataclass_types(cls)
    all_fields = get_all_fields(cls)
    return (
        types,
        tuple(f for f in all_fields.values() if f.name not in init_only),
        tuple(f for f in all_fields.values() if f.name in init_only),
    )


class Unsupported(TypeError):
    def __init__(self, cls: Type):
        self.cls = cls


Return = TypeVar("Return", covariant=True)


class Visitor(Generic[Return]):
    def __init__(self):
        self._type_vars = TypeVarResolver()

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

    def _generic(self, cls: AnyType) -> Return:
        with self._type_vars.generic_context(cls):
            return self.visit(cls.__origin__)

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

    def _type_var(self, tv: AnyType) -> Return:
        with self._type_vars.resolve_context(tv) as cls:
            return self.visit(cls)

    def _merge_union(self, alternatives: Iterable[Return]) -> Return:
        raise NotImplementedError()

    def union(self, alternatives: Sequence[AnyType]) -> Return:
        return self._merge_union(map(self.visit, alternatives))

    def unsupported(self, cls: AnyType) -> Return:
        raise Unsupported(cls) from None

    def visit(self, cls: AnyType) -> Return:
        if cls in PRIMITIVE_TYPES:
            return self.primitive(cls)
        origin = get_origin(cls)
        if origin is not None:
            args = get_args(cls)
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
            # TypeVar handling
            if not hasattr(origin, "__parameters__"):  # pragma: no cover
                return self.unsupported(origin)
            return self._generic(cls)
        if hasattr(cls, "__supertype__"):
            return self.new_type(cls, cls.__supertype__)
        if isinstance(cls, TypeVar):  # type: ignore
            return self._type_var(cls)
        if cls is Any:
            return self.any()
        if cls in COLLECTION_TYPES:
            return self.collection(cls, Any)
        if cls in MAPPING_TYPES:
            return self.mapping(cls, Any, Any)
        if isinstance(cls, _LiteralMeta):  # pragma: no cover py36
            return self.literal(cls.__values__)  # type: ignore
        # cannot use isinstance(..., TypedDict)
        if isinstance(cls, _TypedDictMeta):
            total = cls.__total__  # type: ignore
            assert isinstance(cls, type)
            return self.typed_dict(cls, type_hints_cache(cls), total)
        return self.visit_not_builtin(cls)

    def visit_not_builtin(self, cls: Type) -> Return:
        if is_dataclass(cls):
            return self.dataclass(cls, *dataclass_types_and_fields(cls))  # type: ignore
        try:
            issubclass(cls, object)
        except TypeError:
            return self.unsupported(cls)
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
        return self.unsupported(cls)
