from abc import ABC, abstractmethod
from dataclasses import is_dataclass
from enum import Enum
from types import FunctionType
from typing import (Any, Generic, Iterable, Mapping, Sequence, Tuple, Type,
                    TypeVar, Union, cast)

from src.model import Model
from src.types import (ITERABLE_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES,
                       Primitive, iterable_type, type_name)

try:
    from typing_extensions import Literal
except ImportError:
    Literal = None  # type: ignore

Path = Tuple[str, ...]

ReturnType = TypeVar("ReturnType")
Context = TypeVar("Context")


class Unsupported(Exception):
    def __init__(self, cls: Type):
        self.cls = cls

    def __str__(self) -> str:
        return f"Unsupported '{type_name(self.cls)}' type"


class Visitor(ABC, Generic[ReturnType, Context]):
    def __init__(self):
        self._generics: Mapping[TypeVar, Type] = {}  # pragma: no cover

    def with_class_context(self, cls: Type, ctx: Context,
                           path: Path) -> Context:
        return ctx  # pragma: no cover

    @abstractmethod
    def any(self, ctx: Context, path: Path) -> ReturnType:
        ...

    @abstractmethod
    def model(self, cls: Type[Model], ctx: Context, path: Path) -> ReturnType:
        ...

    @abstractmethod
    def optional(self, value: Type, ctx: Context, path: Path) -> ReturnType:
        ...

    @abstractmethod
    def union(self, alternatives: Iterable[Type], ctx: Context,
              path: Path) -> ReturnType:
        ...

    @abstractmethod
    def iterable(self, cls: Type[Iterable], value_type: Type, ctx: Context,
                 path: Path) -> ReturnType:
        ...

    @abstractmethod
    def mapping(self, key_type: Type, value_type: Type, ctx: Context,
                path: Path) -> ReturnType:
        ...

    @abstractmethod
    def primitive(self, cls: Primitive, ctx: Context,
                  path: Path) -> ReturnType:
        ...

    @abstractmethod
    def dataclass(self, cls: Type, ctx: Context, path: Path) -> ReturnType:
        ...

    @abstractmethod
    def enum(self, cls: Type[Enum], ctx: Context, path: Path) -> ReturnType:
        ...

    @abstractmethod
    def literal(self, values: Sequence[Any], ctx: Context,
                path: Path) -> ReturnType:
        ...

    def visit(self, cls: Type, ctx: Context, path: Path) -> ReturnType:
        if cls in PRIMITIVE_TYPES:
            return self.primitive(cast(Primitive, cls), ctx, path)
        if hasattr(cls, "__origin__"):
            origin = cls.__origin__  # type: ignore
            # noinspection PyUnresolvedReferences
            args = cls.__args__  # type: ignore
            if origin is Union:
                if len(args) == 2 and type(None) in args:
                    return self.optional(args[0], ctx, path)
                else:
                    return self.union(args, ctx, path)
            if origin in ITERABLE_TYPES:
                # noinspection PyTypeChecker
                return self.iterable(iterable_type(origin), args[0], ctx, path)
            if origin in MAPPING_TYPES:
                return self.mapping(args[0], args[1], ctx, path)
            if Literal is not None and origin is Literal:
                return self.literal(args, ctx, path)
            try:
                generics_items = zip((p for p in origin.__parameters__), args)
            except AttributeError:
                raise Unsupported(cls)
            generics_save = self._generics
            self._generics = {}
            for tv, value in generics_items:
                self._generics[tv] = generics_save.get(value, value)
            res = self.visit(origin, ctx, path)
            self._generics = generics_save
            return res
        try:
            if issubclass(cls, Model):
                return self.model(cls, self.with_class_context(cls, ctx, path),
                                  path)
            if is_dataclass(cls):
                return self.dataclass(
                    cls, self.with_class_context(cls, ctx, path), path
                )
            if issubclass(cls, Enum):
                # noinspection PyTypeChecker
                return self.enum(cls, ctx, path)
        except TypeError:  # because of 'issubclass'
            pass
        if cls is Any:
            return self.any(ctx, path)
        # new type handling
        if isinstance(cls, FunctionType):
            if hasattr(cls, "__supertype__"):
                return self.visit(cls.__supertype__, ctx, path)
            else:
                raise Unsupported(cls)
        if isinstance(cls, TypeVar):  # type: ignore
            # TODO catch key error (when a generic is not specified)
            return self.visit(self._generics[cls], ctx, path)
        raise Unsupported(cls)
