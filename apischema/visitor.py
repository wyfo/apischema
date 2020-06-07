from collections import defaultdict
from dataclasses import is_dataclass
from enum import Enum
from typing import (
    Any,
    Callable,
    Collection,
    DefaultDict,
    Generic,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.types import (
    AnyType,
    COLLECTION_TYPES,
    MAPPING_TYPES,
    OrderedDict,
    PRIMITIVE_TYPES,
    TUPLE_TYPE,
)
from apischema.typing import Literal, _AnnotatedAlias, _LiteralMeta, _TypedDictMeta
from apischema.utils import type_hints_cache

PRIMITIVE_TYPE_IDS = set(map(id, PRIMITIVE_TYPES))


class Unsupported(TypeError):
    def __init__(self, cls: Type):
        self.cls = cls


Arg = TypeVar("Arg", contravariant=True)
Return = TypeVar("Return", covariant=True)


class Visitor(Generic[Arg, Return]):
    def __init__(self):
        self._generics: DefaultDict[TypeVar, List[AnyType]] = defaultdict(list)

    def annotated(self, cls: AnyType, annotations: Sequence[Any], arg: Arg) -> Return:
        return self.visit(cls, arg)

    def any(self, arg: Arg) -> Return:
        raise NotImplementedError()

    def collection(
        self, cls: Type[Collection], value_type: AnyType, arg: Arg
    ) -> Return:
        raise NotImplementedError()

    def dataclass(self, cls: Type, arg: Arg) -> Return:
        raise NotImplementedError()

    def enum(self, cls: Type[Enum], arg: Arg) -> Return:
        raise NotImplementedError()

    def _generic(self, cls: AnyType, arg: Arg) -> Return:
        origin, args = cls.__origin__, cls.__args__
        assert len(origin.__parameters__) == len(args)
        # Use a side effect in order to avoid passing argument anywhere
        for tv, value in zip(origin.__parameters__, args):
            self._generics[tv].append(value)
        try:
            return self.visit(origin, arg)
        finally:
            for tv in origin.__parameters__:
                self._generics[tv].pop()

    def literal(self, values: Sequence[Any], arg: Arg) -> Return:
        raise NotImplementedError()

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType, arg: Arg
    ) -> Return:
        raise NotImplementedError()

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
        arg: Arg,
    ) -> Return:
        raise NotImplementedError("NamedTuple is not handled")

    def new_type(self, cls: AnyType, super_type: AnyType, arg: Arg) -> Return:
        return self.visit(super_type, arg)

    def primitive(self, cls: Type, arg: Arg) -> Return:
        raise NotImplementedError()

    def subprimitive(self, cls: Type, superclass: Type, arg: Arg) -> Return:
        return self.primitive(superclass, arg)

    def tuple(self, types: Sequence[AnyType], arg: Arg) -> Return:
        raise NotImplementedError()

    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool, arg: Arg
    ) -> Return:
        raise NotImplementedError()

    def _type_var(self, tv: AnyType, arg: Arg) -> Return:
        try:
            cls_ = self._generics[tv].pop()
        except IndexError:
            if tv.__constraints__:
                return self.visit(Union[tv.__constraints__], arg)
            else:
                return self.visit(Any, arg)
        try:
            return self.visit(cls_, arg)
        finally:
            self._generics[tv].append(cls_)

    def union(self, alternatives: Sequence[AnyType], arg: Arg) -> Return:
        raise NotImplementedError()

    def _unsupported(self, cls: AnyType, arg: Arg) -> Return:
        if hasattr(cls, "__parameters__") and cls.__parameters__:
            params = tuple(
                (self._generics[p] or [Any])[-1] for p in getattr(cls, "__parameters__")
            )
            if len(params) == 1:
                params = params[0]
            return self.unsupported(cls[params], arg)
        else:
            return self.unsupported(cls, arg)

    def unsupported(self, cls: AnyType, arg: Arg) -> Return:
        raise Unsupported(cls) from None

    def visit(self, cls: AnyType, arg: Arg) -> Return:
        # Use `id` to avoid useless costly generic types hashing
        if id(cls) in PRIMITIVE_TYPE_IDS:
            return self.primitive(cls, arg)
        origin = getattr(cls, "__origin__", None)  # because of 3.6
        if origin is not None:
            if isinstance(cls, _AnnotatedAlias):
                return self.annotated(cls.__args__[0], cls.__metadata__, arg)
            if origin is Union:
                return self.union(cls.__args__, arg)
            if origin is TUPLE_TYPE:
                if len(cls.__args__) < 2 or cls.__args__[1] is not ...:
                    return self.tuple(cls.__args__, arg)
            if origin in COLLECTION_TYPES:
                return self.collection(origin, cls.__args__[0], arg)
            if origin in MAPPING_TYPES:
                return self.mapping(origin, cls.__args__[0], cls.__args__[1], arg)
            if origin is Literal:  # pragma: no cover (because of py36)
                return self.literal(cls.__args__, arg)
            # TypeVar handling
            if not hasattr(origin, "__parameters__"):  # pragma: no cover
                return self.unsupported(origin, arg)
            return self._generic(cls, arg)
        if hasattr(cls, "__supertype__"):
            return self.new_type(cls, cls.__supertype__, arg)
        if isinstance(cls, TypeVar):  # type: ignore
            return self._type_var(cls, arg)
        if cls is Any:
            return self.any(arg)
        # cannot use isinstance(..., TypedDict)
        if isinstance(cls, _TypedDictMeta):
            total = cls.__total__  # type: ignore
            assert isinstance(cls, type)
            return self.typed_dict(cls, type_hints_cache(cls), total, arg)
        return self.visit_not_builtin(cls, arg)

    def visit_not_builtin(self, cls: Type, arg: Arg) -> Return:
        if is_dataclass(cls):
            return self.dataclass(cls, arg)
        # cannot use issubclass before Any or 3.6 Literal
        if isinstance(cls, _LiteralMeta):  # pragma: no cover (because of py36)
            return self.literal(cls.__values__, arg)  # type: ignore
        try:
            issubclass(cls, object)
        except TypeError:
            return self._unsupported(cls, arg)
        if issubclass(cls, Enum):
            return self.enum(cls, arg)
        for primitive in PRIMITIVE_TYPES:
            if issubclass(cls, primitive):
                return self.subprimitive(cls, primitive, arg)
        # NamedTuple
        if issubclass(cls, tuple) and hasattr(cls, "_fields"):
            if hasattr(cls, "__annotations__"):
                types = type_hints_cache(cls)
            elif hasattr(cls, "__field_types"):  # pragma: no cover
                types = cls._field_types  # type: ignore
            else:  # pragma: no cover
                types = OrderedDict((f, Any) for f in cls._fields)  # type: ignore
            return self.named_tuple(
                cls, types, cls._field_defaults, arg  # type: ignore
            )
        return self._unsupported(cls, arg)


class VisitorMock:
    def __init__(self):
        self._method = None
        self._args = None

    def __getattr__(self, name):
        def set_method(*args):
            assert args[-1] is ...
            self._method = name
            self._args = args[:-1]

        return set_method

    def compute_method(
        self, cls: AnyType, visitor_cls: Optional[Type[Visitor]]
    ) -> Callable[[Visitor[Arg, Return], AnyType, Arg], Return]:
        Visitor.visit(cast(Visitor, self), cls, ...)
        method_name, args = self._method, self._args
        assert method_name is not None and args is not None
        if visitor_cls is None:

            def method(visitor: Visitor[Arg, Return], cls: AnyType, arg: Arg) -> Return:
                return getattr(visitor, method_name)(*args, arg)

        else:
            _method = getattr(visitor_cls, method_name)
            if args == (cls,):
                method = _method
            else:

                def method(
                    visitor: Visitor[Arg, Return], cls: AnyType, arg: Arg
                ) -> Return:
                    return _method(visitor, *args, arg)

        return method


def visitor_method(
    cls: AnyType, visitor_cls: Type[Visitor] = None
) -> Callable[[Visitor[Arg, Return], AnyType, Arg], Return]:
    return VisitorMock().compute_method(cls, visitor_cls)
