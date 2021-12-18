import warnings
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
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    OrderedDict,
    PRIMITIVE_TYPES,
)
from apischema.typing import (
    get_args,
    get_origin,
    get_type_hints,
    is_annotated,
    is_literal,
    is_named_tuple,
    is_type_var,
    is_typed_dict,
    is_union,
    required_keys,
    resolve_type_hints,
)
from apischema.utils import PREFIX, get_origin_or_type, has_type_vars, is_dataclass

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

TUPLE_TYPE = get_origin(Tuple[Any])


def dataclass_types_and_fields(
    tp: AnyType,
) -> Tuple[Mapping[str, AnyType], Sequence[Field], Sequence[Field]]:
    from apischema.metadata.keys import INIT_VAR_METADATA

    cls = get_origin_or_type(tp)
    assert is_dataclass(cls)
    types = resolve_type_hints(tp)
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
    def __init__(self, tp: AnyType):
        self.type = tp

    @property
    def cls(self) -> AnyType:
        warnings.warn(
            "Unsupported.cls is deprecated, use Unsupported.type instead",
            DeprecationWarning,
        )
        return self.type


Result = TypeVar("Result", covariant=True)


class Visitor(Generic[Result]):
    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Result:
        if Unsupported in annotations:
            raise Unsupported(Annotated[(tp, *annotations)])  # type: ignore
        return self.visit(tp)

    def any(self) -> Result:
        raise NotImplementedError

    def collection(self, cls: Type[Collection], value_type: AnyType) -> Result:
        raise NotImplementedError

    def dataclass(
        self,
        tp: AnyType,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Result:
        raise NotImplementedError

    def enum(self, cls: Type[Enum]) -> Result:
        raise NotImplementedError

    def literal(self, values: Sequence[Any]) -> Result:
        raise NotImplementedError

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Result:
        raise NotImplementedError

    def named_tuple(
        self, tp: AnyType, types: Mapping[str, AnyType], defaults: Mapping[str, Any]
    ) -> Result:
        raise NotImplementedError

    def new_type(self, tp: AnyType, super_type: AnyType) -> Result:
        return self.visit(super_type)

    def primitive(self, cls: Type) -> Result:
        raise NotImplementedError

    def subprimitive(self, cls: Type, superclass: Type) -> Result:
        return self.primitive(superclass)

    def tuple(self, types: Sequence[AnyType]) -> Result:
        raise NotImplementedError

    def typed_dict(
        self, tp: AnyType, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> Result:
        raise NotImplementedError

    def union(self, alternatives: Sequence[AnyType]) -> Result:
        raise NotImplementedError

    def unsupported(self, tp: AnyType) -> Result:
        raise Unsupported(tp)

    def visit(self, tp: AnyType) -> Result:
        origin, args = get_origin_or_type(tp), get_args(tp)
        if args:
            if is_annotated(tp):
                return self.annotated(args[0], args[1:])
            if is_union(origin):
                return self.union(args[0]) if len(args) == 1 else self.union(args)
            if origin is TUPLE_TYPE:
                if len(args) < 2 or args[1] is not ...:
                    return self.tuple(args)
            if origin in COLLECTION_TYPES:
                return self.collection(origin, args[0])
            if origin in MAPPING_TYPES:
                return self.mapping(origin, args[0], args[1])
            if is_literal(tp):  # pragma: no cover py37+
                return self.literal(args)
        if origin in PRIMITIVE_TYPES:
            return self.primitive(origin)
        if is_dataclass(origin):
            return self.dataclass(tp, *dataclass_types_and_fields(tp))  # type: ignore
        if hasattr(origin, "__supertype__"):
            return self.new_type(origin, origin.__supertype__)
        if origin is Any:
            return self.any()
        if origin in COLLECTION_TYPES:
            return self.collection(origin, Any)
        if origin in MAPPING_TYPES:
            return self.mapping(origin, Any, Any)
        if isinstance(origin, type):
            if issubclass(origin, Enum):
                return self.enum(origin)
            for primitive in PRIMITIVE_TYPES:
                if issubclass(origin, primitive):
                    return self.subprimitive(origin, primitive)
            # NamedTuple
            if is_named_tuple(origin):
                if hasattr(origin, "__annotations__"):
                    types = resolve_type_hints(origin)
                elif hasattr(origin, "__field_types"):  # pragma: no cover
                    types = origin.__field_types  # type: ignore
                else:  # pragma: no cover
                    types = OrderedDict((f, Any) for f in origin._fields)  # type: ignore  # noqa: E501
                return self.named_tuple(
                    origin, types, origin._field_defaults  # type: ignore
                )
        if is_literal(origin):  # pragma: no cover py36
            return self.literal(origin.__values__)  # type: ignore
        if is_typed_dict(origin):
            return self.typed_dict(
                origin, resolve_type_hints(origin), required_keys(origin)
            )
        if is_type_var(origin):
            if origin.__constraints__:
                return self.visit(Union[origin.__constraints__])
            else:
                return self.any()
        return self.unsupported(tp)
