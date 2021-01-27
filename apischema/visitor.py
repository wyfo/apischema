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
    get_type_hints2,
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
    return MappingProxyType(get_type_hints2(obj))


class Unsupported(TypeError):
    def __init__(self, cls: Type):
        self.cls = cls


Return = TypeVar("Return", covariant=True)


class Visitor(Generic[Return]):
    def __init__(self):
        self._generic: Optional[AnyType] = None

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Return:
        return self.visit(tp)

    def any(self) -> Return:
        raise NotImplementedError

    def collection(self, cls: Type[Collection], value_type: AnyType) -> Return:
        raise NotImplementedError

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Return:
        raise NotImplementedError

    def enum(self, cls: Type[Enum]) -> Return:
        raise NotImplementedError

    def generic(self, tp: AnyType) -> Return:
        _generic = self._generic
        self._generic = tp
        try:
            return self._visit(get_origin(tp))
        finally:
            self._generic = _generic

    def literal(self, values: Sequence[Any]) -> Return:
        raise NotImplementedError

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Return:
        raise NotImplementedError

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> Return:
        raise NotImplementedError

    def new_type(self, tp: AnyType, super_type: AnyType) -> Return:
        return self.visit(super_type)

    def primitive(self, cls: Type) -> Return:
        raise NotImplementedError

    def subprimitive(self, cls: Type, superclass: Type) -> Return:
        return self.primitive(superclass)

    def tuple(self, types: Sequence[AnyType]) -> Return:
        raise NotImplementedError

    def typed_dict(self, cls: Type, keys: Mapping[str, AnyType], total: bool) -> Return:
        raise NotImplementedError

    def _union_result(self, results: Iterable[Return]) -> Return:
        raise NotImplementedError

    def union(self, alternatives: Sequence[AnyType]) -> Return:
        return self._union_result(map(self.visit, alternatives))

    def unsupported(self, tp: AnyType) -> Return:
        raise Unsupported(tp)

    def _visit_generic(self, tp: AnyType) -> Return:
        origin, args = get_origin(tp), get_args(tp)
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
        return self.generic(tp)

    def _visit(self, tp: AnyType) -> Return:
        if tp in PRIMITIVE_TYPES:
            return self.primitive(tp)
        if is_dataclass(tp):
            return self.dataclass(
                tp, *dataclass_types_and_fields(self._generic or tp)  # type: ignore
            )
        if hasattr(tp, "__supertype__"):
            return self.new_type(tp, tp.__supertype__)
        if tp is Any:
            return self.any()
        if tp in COLLECTION_TYPES:
            return self.collection(tp, Any)
        if tp in MAPPING_TYPES:
            return self.mapping(tp, Any, Any)
        try:
            issubclass(tp, object)
        except TypeError:
            pass
        else:
            if issubclass(tp, Enum):
                return self.enum(tp)
            for primitive in PRIMITIVE_TYPES:
                if issubclass(tp, primitive):
                    return self.subprimitive(tp, primitive)
            # NamedTuple
            if issubclass(tp, tuple) and hasattr(tp, "_fields"):
                if hasattr(tp, "__annotations__"):
                    types = type_hints_cache(self._generic or tp)
                elif hasattr(tp, "__field_types"):  # pragma: no cover
                    types = tp._field_types  # type: ignore
                else:  # pragma: no cover
                    types = OrderedDict((f, Any) for f in tp._fields)  # type: ignore
                return self.named_tuple(tp, types, tp._field_defaults)  # type: ignore
        if isinstance(tp, _LiteralMeta):  # pragma: no cover py36
            return self.literal(tp.__values__)  # type: ignore
        # cannot use issubclass(..., TypedDict)
        if isinstance(tp, _TypedDictMeta):
            total = tp.__total__  # type: ignore
            assert isinstance(tp, type)
            return self.typed_dict(tp, type_hints_cache(self._generic or tp), total)
        return self.unsupported(tp)

    def visit(self, tp: AnyType) -> Return:
        if get_origin(tp) is not None:
            return self._visit_generic(tp)
        if is_type_var(tp):
            if tp.__constraints__:
                return self.visit(Union[tp.__constraints__])
            else:
                return self.visit(Any)
        else:
            _generic = self._generic
            self._generic = None
            try:
                return self._visit(tp)
            finally:
                self._generic = _generic
