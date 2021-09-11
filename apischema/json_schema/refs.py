from collections import defaultdict
from enum import Enum
from typing import (
    Any,
    Collection,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.visitor import (
    ConversionsVisitor,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.json_schema.conversions_resolver import WithConversionsResolver
from apischema.objects import ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.type_names import TypeNameFactory, get_type_name
from apischema.types import AnyType
from apischema.utils import is_hashable, replace_builtins
from apischema.visitor import Unsupported

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Refs = Dict[str, Tuple[AnyType, int]]


class Recursive(Exception):
    pass


T = TypeVar("T")


class RefsExtractor(ConversionsVisitor, ObjectVisitor, WithConversionsResolver):
    def __init__(self, default_conversion: DefaultConversion, refs: Refs):
        super().__init__(default_conversion)
        self.refs = refs
        self._rec_guard: Dict[
            Tuple[AnyType, Optional[AnyConversion]], int
        ] = defaultdict(lambda: 0)

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
        return super().annotated(tp, annotations)

    def any(self):
        pass

    def collection(self, cls: Type[Collection], value_type: AnyType):
        self.visit(value_type)

    def enum(self, cls: Type[Enum]):
        pass

    def literal(self, values: Sequence[Any]):
        pass

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType):
        self.visit(key_type)
        self.visit(value_type)

    def object(self, tp: AnyType, fields: Sequence[ObjectField]):
        for field in fields:
            self.visit_with_conv(field.type, self._field_conversion(field))

    def primitive(self, cls: Type):
        pass

    def tuple(self, types: Sequence[AnyType]):
        for cls in types:
            self.visit(cls)

    def _visited_union(self, results: Sequence):
        pass

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Any],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ):
        ref_types = []
        if not dynamic:
            for ref_tp in self.resolve_conversion(tp):
                ref_types.append(ref_tp)
                if self._incr_ref(get_type_name(ref_tp).json_schema, ref_tp):
                    return
        if not is_hashable(tp):
            return super().visit_conversion(tp, conversion, dynamic, next_conversion)
        # 2 because the first type encountered of the recursive cycle can have no ref
        # (see test_recursive_by_conversion_schema)
        if self._rec_guard[(tp, self._conversion)] > 2:
            raise TypeError(f"Recursive type {tp} need a ref")
        self._rec_guard[(tp, self._conversion)] += 1
        try:
            super().visit_conversion(tp, conversion, dynamic, next_conversion)
        except Unsupported:
            for ref_tp in ref_types:
                self.refs.pop(get_type_name(ref_tp).json_schema, ...)  # type: ignore
        finally:
            self._rec_guard[(tp, self._conversion)] -= 1


class DeserializationRefsExtractor(
    RefsExtractor, DeserializationVisitor, DeserializationObjectVisitor
):
    pass


class SerializationRefsExtractor(
    RefsExtractor, SerializationVisitor, SerializationObjectVisitor
):
    pass
