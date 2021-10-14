from dataclasses import Field
from enum import Enum
from typing import Any, Collection, Dict, Mapping, Optional, Sequence, Set, Tuple, Type

from apischema.cache import cache
from apischema.conversions import AnyConversion
from apischema.conversions.conversions import DefaultConversion
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.types import AnyType
from apischema.utils import Lazy
from apischema.visitor import Result


class RecursionGuard(Set[Tuple[AnyType, Optional[AnyConversion]]]):
    def __hash__(self):
        return hash(None)

    def __eq__(self, other):
        return isinstance(other, RecursionGuard)


class RecursiveChecker(ConversionsVisitor[Conv, bool]):
    def __init__(self, default_conversion: DefaultConversion, guard: RecursionGuard):
        super().__init__(default_conversion)
        self.guard = guard
        self._first_visit = True

    def any(self) -> bool:
        return False

    def collection(self, cls: Type[Collection], value_type: AnyType) -> bool:
        return self.visit(value_type)

    def dataclass(
        self,
        tp: AnyType,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> bool:
        # It's possible to have type without associated field, e.g. an annotation of an
        # inherited class, so don't map types.values()
        return any(map(self.visit, (types[f.name] for f in (*fields, *init_vars))))

    def enum(self, cls: Type[Enum]) -> bool:
        return False

    def literal(self, values: Sequence[Any]) -> bool:
        return False

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> bool:
        return self.visit(key_type) or self.visit(value_type)

    def named_tuple(
        self, tp: AnyType, types: Mapping[str, AnyType], defaults: Mapping[str, Any]
    ) -> bool:
        return any(map(self.visit, types.values()))

    def primitive(self, cls: Type) -> bool:
        return False

    def tuple(self, types: Sequence[AnyType]) -> bool:
        return any(map(self.visit, types))

    def typed_dict(
        self, tp: AnyType, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> bool:
        return any(map(self.visit, types))

    def _visited_union(self, results: Sequence[bool]) -> bool:
        return any(results)

    def unsupported(self, tp: AnyType) -> bool:
        return False

    def visit(self, tp: AnyType) -> bool:
        if self._first_visit:
            self._first_visit = False
            return super().visit(tp)
        return _is_recursive_type(
            tp, self.__class__, self._conversion, self.default_conversion, self.guard
        )


class DeserializationRecursiveChecker(
    DeserializationVisitor[bool], RecursiveChecker[Deserialization]
):
    pass


class SerializationRecursiveChecker(
    SerializationVisitor[bool], RecursiveChecker[SerializationVisitor]
):
    pass


@cache
def _is_recursive_type(
    tp: AnyType,
    checker: Type[RecursiveChecker],
    conversion: Optional[AnyConversion],
    default_conversions: DefaultConversion,
    sentinel: RecursionGuard,
) -> bool:
    recursion_key = tp, conversion
    if recursion_key in sentinel:
        return True
    sentinel.add(recursion_key)
    try:
        return checker(default_conversions, sentinel).visit_with_conv(tp, conversion)
    finally:
        sentinel.remove(recursion_key)


def is_recursive_type(tp: AnyType, visitor: ConversionsVisitor):
    return _is_recursive_type(
        tp,
        DeserializationRecursiveChecker  # type: ignore
        if isinstance(visitor, DeserializationVisitor)
        else SerializationRecursiveChecker,
        visitor._conversion,
        visitor.default_conversion,
        RecursionGuard(),
    )


class RecursiveConversionsVisitor(ConversionsVisitor[Conv, Result]):
    def __init__(self, default_conversion: DefaultConversion):
        super().__init__(default_conversion)
        self._cache: Dict[Tuple[AnyType, Optional[AnyConversion]], Result] = {}
        self._first_visit = True

    def _recursive_result(self, lazy: Lazy[Result]) -> Result:
        raise NotImplementedError

    def visit_not_recursive(self, tp: AnyType) -> Result:
        return super().visit(tp)

    def visit(self, tp: AnyType) -> Result:
        if is_recursive_type(tp, self):
            cache_key = tp, self._conversion
            if cache_key in self._cache:
                return self._cache[cache_key]
            result = None

            def lazy_result():
                assert result is not None
                return result

            self._cache[cache_key] = self._recursive_result(lazy_result)
            try:
                result = super().visit(tp)
            finally:
                del self._cache[cache_key]
            return result
        elif self._first_visit:
            self._first_visit = False
            return super().visit(tp)
        else:
            return self.visit_not_recursive(tp)
