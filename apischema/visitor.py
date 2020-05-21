from dataclasses import is_dataclass
from enum import Enum, EnumMeta
from typing import Any, Dict, Generic, Iterable, Mapping, Sequence, Type, TypeVar, Union

from apischema.types import ITERABLE_TYPES, MAPPING_TYPES, PRIMITIVE_TYPE
from apischema.typing import (
    Literal,
    NamedTupleMeta,
    _AnnotatedAlias,
    _LiteralMeta,
    _TypedDictMeta,
    _type_repr,
    get_type_hints,
)

PRIMITIVE_TYPE_IDS = set(map(id, PRIMITIVE_TYPE))


class Unsupported(TypeError):
    def __init__(self, cls: Type):
        self.cls = cls

    def __repr__(self):
        return f"unsupported '{_type_repr(self.cls)}' type"


class NotCustom:
    pass


NOT_CUSTOM = NotCustom()

Arg = TypeVar("Arg", contravariant=True)
Return = TypeVar("Return", covariant=True)


class Visitor(Generic[Arg, Return]):
    def __init__(self):
        self._generics: Dict[TypeVar, Type] = {}

    def primitive(self, cls: Type, arg: Arg) -> Return:
        raise NotImplementedError()

    def union(self, alternatives: Sequence[Type], arg: Arg) -> Return:
        raise NotImplementedError()

    def iterable(self, cls: Type[Iterable], value_type: Type, arg: Arg) -> Return:
        raise NotImplementedError()

    def mapping(
        self, cls: Type[Mapping], key_type: Type, value_type: Type, arg: Arg
    ) -> Return:
        raise NotImplementedError()

    def typed_dict(
        self, cls: Type, keys: Mapping[str, Type], total: bool, arg: Arg
    ) -> Return:
        raise NotImplementedError()

    def tuple(self, types: Sequence[Type], arg: Arg) -> Return:
        raise NotImplementedError()

    def literal(self, values: Sequence[Any], arg: Arg) -> Return:
        raise NotImplementedError()

    def custom(self, cls: Type, arg: Arg) -> Union[Return, NotCustom]:
        return NOT_CUSTOM

    def dataclass(self, cls: Type, arg: Arg) -> Return:
        raise NotImplementedError()

    def enum(self, cls: Type[Enum], arg: Arg) -> Return:
        raise NotImplementedError()

    def new_type(self, cls: Type, super_type: Type, arg: Arg) -> Return:
        return self.visit(super_type, arg)

    def any(self, arg: Arg) -> Return:
        raise NotImplementedError()

    def annotated(self, cls: Type, annotations: Sequence[Any], arg: Arg) -> Return:
        return self.visit(cls, arg)

    def named_tuple(
        self,
        cls: Type,
        types: Mapping[str, Type],
        defaults: Mapping[str, Any],
        arg: Arg,
    ) -> Return:
        raise TypeError("NamedTuple is not handled")

    def visit(self, cls: Type, arg: Arg) -> Return:
        # Use `id` to avoid useless costly generic types hashing
        if id(cls) in PRIMITIVE_TYPE_IDS:
            return self.primitive(cls, arg)
        origin = getattr(cls, "__origin__", None)  # because of 3.6
        if origin is not None:
            if isinstance(cls, _AnnotatedAlias):
                return self.annotated(origin, cls.__metadata__, arg)
            if origin is Union:
                return self.union(cls.__args__, arg)
            if origin is tuple:
                if len(cls.__args__) < 2 or cls.__args__[1] is not ...:
                    return self.tuple(cls.__args__, arg)
            if origin in ITERABLE_TYPES:
                return self.iterable(origin, cls.__args__[0], arg)
            if origin in MAPPING_TYPES:
                return self.mapping(origin, cls.__args__[0], cls.__args__[1], arg)
            if origin is Literal:
                return self.literal(cls.__args__, arg)
            custom = self.custom(cls, arg)
            if custom is not NOT_CUSTOM:
                assert not isinstance(custom, NotCustom)
                return custom
            # TypeVar handling
            generics_save = self._generics.copy()
            for tv, value in zip(origin.__parameters__, cls.__args__):
                # Kind of ugly side effect, but for simplicity
                self._generics[tv] = generics_save.get(value, value)
            res = self.visit(origin, arg)
            self._generics = generics_save
            return res
        # customs are handled before other classes
        custom = self.custom(cls, arg)
        if custom is not NOT_CUSTOM:
            assert not isinstance(custom, NotCustom)
            return custom
        if is_dataclass(cls):
            return self.dataclass(cls, arg)
        if isinstance(cls, _TypedDictMeta):
            total = cls.__total__  # type: ignore
            return self.typed_dict(
                cls, get_type_hints(cls, include_extras=True), total, arg
            )
        if isinstance(cls, TypeVar):  # type: ignore
            try:
                cls_ = self._generics[cls]
            except KeyError:
                if cls.__constraints__:
                    return self.visit(Union[cls.__constraints__], arg)
                return self.visit(Any, arg)  # type: ignore
            else:
                return self.visit(cls_, arg)
        if isinstance(cls, EnumMeta):
            return self.enum(cls, arg)
        if hasattr(cls, "__supertype__"):
            return self.new_type(cls, cls.__supertype__, arg)
        if cls is Any:
            return self.any(arg)
        if isinstance(cls, NamedTupleMeta):
            if hasattr(cls, "__annotations__"):
                types = get_type_hints(cls, include_extras=True)
            else:
                types = cls._field_types  # type: ignore
            return self.named_tuple(cls, types, cls._field_defaults, arg)
        if isinstance(cls, _LiteralMeta):
            return self.literal(cls.__values__, arg)
        if hasattr(cls, "__parameters__"):
            params = tuple(
                self._generics.get(p, Any) for p in getattr(cls, "__parameters__")
            )
            raise Unsupported(cls[params])
        raise Unsupported(cls)
