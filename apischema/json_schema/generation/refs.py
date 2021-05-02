from contextlib import suppress
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Type

from apischema.conversions.visitor import (
    ConversionsVisitor,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.objects import ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.type_names import TypeName, check_type_with_name, get_type_name
from apischema.types import AnyType, UndefinedType
from apischema.utils import contains

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Refs = Dict[str, Tuple[AnyType, int]]


class Recursive(Exception):
    pass


class RefsExtractor(ObjectVisitor, ConversionsVisitor):
    def __init__(self, refs: Refs):
        super().__init__()
        self.refs = refs
        self._rec_guard: Dict[AnyType, bool] = {}

    def _incr_ref(self, ref: Optional[str], tp: AnyType) -> bool:
        if ref is None:
            return False
        else:
            ref_cls, count = self.refs.get(ref, (tp, 0))
            if ref_cls != tp:
                raise ValueError(
                    f"Types {tp} and {self.refs[ref][0]} share same reference '{ref}'"
                )
            self.refs[ref] = (ref_cls, count + 1)
            return count > 0

    def annotated(self, tp: AnyType, annotations: Sequence[Any]):
        for i, annotation in enumerate(reversed(annotations)):
            if isinstance(annotation, TypeName):
                check_type_with_name(tp)
                ref = annotation.json_schema
                if not isinstance(ref, str):
                    raise ValueError("Annotated type_name can only be str")
                ref_annotations = annotations[: len(annotations) - i]
                annotated = Annotated[(tp, *ref_annotations)]  # type: ignore
                if self._incr_ref(ref, annotated):
                    return
        return self.visit(tp)

    def any(self):
        pass

    def collection(self, cls: Type[Iterable], value_type: AnyType):
        return self.visit(value_type)

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

    def visit(self, tp: AnyType):
        dynamic = self._apply_dynamic_conversions(tp)
        ref_tp = dynamic if dynamic is not None else tp
        if not self._incr_ref(get_type_name(ref_tp).json_schema, ref_tp):
            if contains(self._rec_guard, ref_tp) and self._rec_guard[ref_tp]:
                raise TypeError(f"Recursive type {tp} need a ref")
            with suppress(TypeError):
                self._rec_guard[ref_tp] = ref_tp in self._rec_guard
            try:
                super().visit(ref_tp)
            finally:
                with suppress(TypeError):
                    if self._rec_guard[ref_tp]:
                        self._rec_guard[ref_tp] = False
                    else:
                        del self._rec_guard[ref_tp]


class DeserializationRefsExtractor(
    DeserializationObjectVisitor, DeserializationVisitor, RefsExtractor
):
    pass


class SerializationRefsExtractor(
    SerializationObjectVisitor, SerializationVisitor, RefsExtractor
):
    pass
