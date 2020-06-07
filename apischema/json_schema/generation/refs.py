from enum import Enum
from typing import (  # type: ignore
    Any,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
)

from apischema.conversion.utils import Conversions
from apischema.json_schema.generation.visitor import SchemaVisitor
from apischema.json_schema.refs import get_ref, schema_ref
from apischema.types import AnyType
from apischema.typing import Annotated
from apischema.utils import is_hashable

Refs = Dict[str, Tuple[AnyType, int]]


class Recursive(Exception):
    pass


class RefsExtractor(SchemaVisitor):
    def __init__(self, conversions: Optional[Conversions], refs: Refs):
        super().__init__(conversions)
        self.refs = refs

    def _incr_ref(self, ref: Optional[str], cls: AnyType) -> bool:
        if ref is not None:
            ref_cls, count = self.refs.get(ref, (cls, 0))
            if ref_cls != cls:
                raise ValueError(
                    f"Types {cls} and {self.refs[ref]} share same reference '{ref}'"
                )
            self.refs[ref] = (ref_cls, count + 1)
            return count > 0
        return False

    def _annotated(self, cls: AnyType, annotations: Sequence[Any], _):
        for annotation in reversed(annotations):
            if isinstance(annotation, schema_ref):
                annotation.check_type(cls)
                ref = annotation.ref
                if not isinstance(ref, str):
                    raise ValueError("Annotated schema_ref can only be str")
                annotated = Annotated[(cls, *filter(is_hashable, annotations))]  # type: ignore # noqa E501
                if self._incr_ref(ref, annotated):
                    return
        return self.visit(cls)

    def any(self, _):
        pass

    def collection(self, cls: Type[Iterable], value_type: AnyType, _):
        return self.visit(value_type)

    def dataclass(self, cls: Type, _):
        (
            fields,
            merged_fields,
            pattern_fields,
            additional_field,
        ) = self._dataclass_fields(cls)
        for field in fields:
            self._field_visit(field, _)
        for _, field in merged_fields:
            self._field_visit(field, _)
        for _, field in pattern_fields:
            self._field_visit(field, _)
        if additional_field:
            self._field_visit(additional_field, _)

    def enum(self, cls: Type[Enum], _):
        pass

    def literal(self, values: Sequence[Any], _):
        pass

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType, _):
        self.visit(key_type)
        self.visit(value_type)

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
        _,
    ):
        for cls in types.values():
            self.visit(cls)

    def new_type(self, cls: AnyType, super_type: AnyType, _):
        self.visit(super_type)

    def primitive(self, cls: Type, _):
        pass

    def subprimitive(self, cls: Type, superclass: Type, _):
        self.visit(superclass)

    def tuple(self, types: Sequence[AnyType], _):
        for cls in types:
            self.visit(cls)

    def typed_dict(self, cls: Type, keys: Mapping[str, AnyType], total: bool, _):
        for cls in keys.values():
            self.visit(cls)

    def _union_arg(self, cls: AnyType, _):
        return None

    def _union_result(self, results: Sequence, _):
        pass

    def visit(self, cls: AnyType, _=None):
        if self._is_conversion(cls):
            return self.visit_not_builtin(cls, _)
        # Annotated is not always hashable
        if is_hashable(cls):
            if self._incr_ref(get_ref(cls), cls):
                return
        super().visit(cls, _)
