from collections import defaultdict
from enum import Enum
from typing import (
    Any,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from apischema.conversions.conversions import ResolvedConversions
from apischema.conversions.visitor import (
    ConversionsVisitor,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.json_schema.generation.conversions_resolver import (
    WithConversionsResolver,
)
from apischema.objects import ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.type_names import TypeNameFactory, get_type_name
from apischema.types import AnyType, UndefinedType
from apischema.utils import replace_builtins

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Refs = Dict[str, Tuple[AnyType, int]]


class Recursive(Exception):
    pass


T = TypeVar("T")


class RefsExtractor(ConversionsVisitor, ObjectVisitor, WithConversionsResolver):
    def __init__(self, refs: Refs):
        super().__init__()
        self.refs = refs
        self._rec_guard: Dict[Tuple[AnyType, ResolvedConversions], int] = defaultdict(
            lambda: 1
        )

    def _incr_ref(self, ref: Optional[str], tp: AnyType) -> bool:
        if ref is None:
            return False
        else:
            ref_cls, count = self.refs.get(ref, (tp, 0))
            if replace_builtins(ref_cls) != replace_builtins(tp):
                raise ValueError(
                    f"Types {tp} and {self.refs[ref][0]} share same reference '{ref}'"
                )
            self.refs[ref] = (ref_cls, count + 1)
            return count > 0

    def annotated(self, tp: AnyType, annotations: Sequence[Any]):
        for i, annotation in enumerate(reversed(annotations)):
            if isinstance(annotation, TypeNameFactory):
                ref = annotation.to_type_name(tp).json_schema
                if not isinstance(ref, str):
                    continue
                ref_annotations = annotations[: len(annotations) - i]
                annotated = Annotated[(tp, *ref_annotations)]  # type: ignore
                if self._incr_ref(ref, annotated):
                    return
        return self.visit(tp)

    def any(self):
        pass

    def collection(self, cls: Type[Iterable], value_type: AnyType):
        self.visit(value_type)

    def enum(self, cls: Type[Enum]):
        pass

    def literal(self, values: Sequence[Any]):
        pass

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType):
        self.visit(key_type)
        self.visit(value_type)

    def new_type(self, tp: AnyType, super_type: AnyType):
        self.visit(super_type)

    def object(self, cls: Type, fields: Sequence[ObjectField]):
        for field in fields:
            self.visit_with_conversions(field.type, self._field_conversion(field))

    def primitive(self, cls: Type):
        pass

    def subprimitive(self, cls: Type, superclass: Type):
        self.visit(superclass)

    def tuple(self, types: Sequence[AnyType]):
        for cls in types:
            self.visit(cls)

    def _union_result(self, results: Iterable):
        for _ in results:
            pass

    def union(self, alternatives: Sequence[AnyType]):
        return super().union([alt for alt in alternatives if alt is not UndefinedType])

    def visit_conversion(self, tp: AnyType, conversion: Optional[Any], dynamic: bool):
        if not dynamic:
            for ref_tp in self.resolve_conversions(tp):
                if self._incr_ref(get_type_name(ref_tp).json_schema, ref_tp):
                    return
        try:
            hash(tp)
        except TypeError:
            return super().visit_conversion(tp, conversion, dynamic)
        # 2 because the first type encountered of the recursive cycle can have no ref
        # (see test_recursive_by_conversion_schema)
        if self._rec_guard[(tp, self._conversions)] > 2:
            raise TypeError(f"Recursive type {tp} need a ref")
        self._rec_guard[(tp, self._conversions)] += 1
        try:
            return super().visit_conversion(tp, conversion, dynamic)
        finally:
            self._rec_guard[(tp, self._conversions)] -= 1


class DeserializationRefsExtractor(
    RefsExtractor, DeserializationVisitor, DeserializationObjectVisitor
):
    pass


class SerializationRefsExtractor(
    RefsExtractor, SerializationVisitor, SerializationObjectVisitor
):
    pass
