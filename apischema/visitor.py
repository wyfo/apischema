from dataclasses import (  # type: ignore
    Field,
    InitVar,
    _FIELDS,
    _FIELD_CLASSVAR,
    make_dataclass,
)
from enum import Enum
from types import MappingProxyType
from typing import (
    Any,
    Collection,
    Generic,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.cache import cache
from apischema.skip import is_skipped
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
    get_type_hints2,
    required_keys,
)
from apischema.utils import (
    PREFIX,
    get_origin_or_type,
    has_type_vars,
    is_dataclass,
    is_type_var,
)

try:
    from apischema.typing import Annotated, Literal
except ImportError:
    Annotated, Literal = ..., ...  # type: ignore

TUPLE_TYPE = get_origin(Tuple[Any])


@cache
def type_hints_cache(obj) -> Mapping[str, AnyType]:
    # Use immutable return because of cache
    return MappingProxyType(get_type_hints2(obj))


@cache
def dataclass_types_and_fields(
    tp: AnyType,
) -> Tuple[Mapping[str, AnyType], Sequence[Field], Sequence[Field]]:
    from apischema.metadata.keys import INIT_VAR_METADATA

    cls = get_origin_or_type(tp)
    assert is_dataclass(cls)
    types = get_type_hints2(tp)
    fields, init_fields = [], []
    for field in getattr(cls, _FIELDS).values():
        assert isinstance(field, Field)
        if field._field_type == _FIELD_CLASSVAR:  # type: ignore
            continue
        field_type = types[field.name]
        if isinstance(field_type, InitVar):
            types[field.name] = field_type.type  # type: ignore
            init_fields.append(field)
        elif field_type is InitVar:
            metadata = getattr(cls, _FIELDS)[field.name].metadata
            if INIT_VAR_METADATA not in metadata:
                raise TypeError("Before 3.8, InitVar requires init_var metadata")
            init_field = (PREFIX, metadata[INIT_VAR_METADATA], ...)
            tmp_cls = make_dataclass("Tmp", [init_field], bases=(cls,))  # type: ignore
            types[field.name] = get_type_hints(tmp_cls, include_extras=True)[PREFIX]
            if has_type_vars(types[field.name]):
                raise TypeError("Generic InitVar are not supported before 3.8")
            init_fields.append(field)
        else:
            fields.append(field)
    # Use immutable return because of cache
    return MappingProxyType(types), tuple(fields), tuple(init_fields)


class Unsupported(TypeError):
    def __init__(self, cls: Type):
        self.cls = cls


Return = TypeVar("Return", covariant=True)


class Visitor(Generic[Return]):
    def __init__(self):
        super().__init__()
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
            return self._visit_not_generic(get_origin(tp))
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

    def typed_dict(
        self, cls: Type, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> Return:
        raise NotImplementedError

    def union(self, alternatives: Sequence[AnyType]) -> Return:
        raise NotImplementedError

    def unsupported(self, tp: AnyType) -> Return:
        raise Unsupported(tp)

    def _visit_generic(self, tp: AnyType) -> Return:
        origin, args = get_origin(tp), get_args(tp)
        assert origin is not None
        if origin is Annotated:
            return self.annotated(args[0], args[1:])
        if origin is Union:
            alternatives = tuple(arg for arg in args if not is_skipped(arg))
            if len(alternatives) == 1:
                return self.visit(alternatives[0])
            else:
                return self.union(alternatives)
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

    def _visit_not_generic(self, tp: AnyType) -> Return:
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
            return self.typed_dict(
                tp, type_hints_cache(self._generic or tp), required_keys(tp)
            )
        return self.unsupported(tp)

    def visit(self, tp: AnyType) -> Return:
        if get_args(tp):
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
                return self._visit_not_generic(tp)
            finally:
                self._generic = _generic
