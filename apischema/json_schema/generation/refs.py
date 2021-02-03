from contextlib import suppress
from dataclasses import Field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Type

from apischema.conversions.visitor import ConversionsVisitor
from apischema.dataclass_utils import get_field_conversions, get_fields
from apischema.json_schema.refs import get_ref, schema_ref
from apischema.skip import filter_skipped
from apischema.types import AnyType
from apischema.utils import contains

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Refs = Dict[str, Tuple[AnyType, int]]


class Recursive(Exception):
    pass


class RefsExtractor(ConversionsVisitor):
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
        for annotation in reversed(annotations):
            if isinstance(annotation, schema_ref):
                annotation.check_type(tp)
                ref = annotation.ref
                if not isinstance(ref, str):
                    raise ValueError("Annotated schema_ref can only be str")
                annotated = Annotated[(tp, *annotations)]  # type: ignore
                if self._incr_ref(ref, annotated):
                    return
        return self.visit(tp)

    def any(self):
        pass

    def collection(self, cls: Type[Iterable], value_type: AnyType):
        return self.visit(value_type)

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ):
        for field in get_fields(fields, init_vars, self.operation):
            self.visit_with_conversions(
                types[field.name], get_field_conversions(field, self.operation)
            )

    def enum(self, cls: Type[Enum]):
        pass

    def literal(self, values: Sequence[Any]):
        pass

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType):
        self.visit(key_type)
        self.visit(value_type)

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ):
        for cls in types.values():
            self.visit(cls)

    def new_type(self, tp: AnyType, super_type: AnyType):
        self.visit(super_type)

    def primitive(self, cls: Type):
        pass

    def subprimitive(self, cls: Type, superclass: Type):
        self.visit(superclass)

    def tuple(self, types: Sequence[AnyType]):
        for cls in types:
            self.visit(cls)

    def typed_dict(self, cls: Type, keys: Mapping[str, AnyType], total: bool):
        for cls in keys.values():
            self.visit(cls)

    def _union_result(self, results: Iterable):
        for _ in results:
            pass

    def union(self, alternatives: Sequence[AnyType]):
        for tp in filter_skipped(alternatives, schema_only=True):
            self.visit(tp)

    def visit(self, tp: AnyType):
        dynamic = self._apply_dynamic_conversions(tp)
        ref_tp = dynamic if dynamic is not None else tp
        if not self._incr_ref(get_ref(ref_tp), ref_tp):
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
