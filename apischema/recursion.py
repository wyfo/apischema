from dataclasses import Field
from enum import Enum
from typing import Any, Collection, Dict, Mapping, Optional, Sequence, Tuple, Type

from apischema.cache import cache
from apischema.conversions import AnyConversion
from apischema.conversions.conversions import DefaultConversion
from apischema.conversions.visitor import Conv, ConversionsVisitor
from apischema.types import AnyType
from apischema.utils import Lazy, is_hashable
from apischema.visitor import Result


class BaseRecursiveConversionsVisitor(ConversionsVisitor[Conv, Result]):
    def __init__(self, default_conversion: DefaultConversion):
        super().__init__(default_conversion)
        self._visit_cache: Dict[Tuple[AnyType, Optional[AnyConversion]], Result] = {}

    def _recursive_result(self, lazy: Lazy[Result]) -> Result:
        raise NotImplementedError

    def is_recursive(self, tp: AnyType) -> bool:
        return is_recursive_type(
            tp, self.base_conversion_visitor, self._conversion, self.default_conversion
        )

    def visit(self, tp: AnyType) -> Result:
        if not is_hashable(tp):
            return super().visit(tp)
        cache_key = (tp, self._conversion)
        if cache_key in self._visit_cache:
            return self._visit_cache[cache_key]
        result = None

        def lazy_result():
            assert result is not None
            return result

        self._visit_cache[cache_key] = self._recursive_result(lazy_result)
        try:
            result = super().visit(tp)
        finally:
            del self._visit_cache[cache_key]
        return result


class RecursiveChecker(BaseRecursiveConversionsVisitor[Conv, bool]):
    def _recursive_result(self, lazy: Lazy[Result]) -> bool:
        return True

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
        return any(map(self.visit, types.values()))

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


@cache
def is_recursive_type(
    tp: AnyType,
    base_visitor: Type[ConversionsVisitor],
    conversion: Optional[AnyConversion],
    default_conversions: DefaultConversion,
):
    class Visitor(RecursiveChecker, base_visitor):  # type: ignore
        pass

    return Visitor(default_conversions).visit_with_conv(tp, conversion)


class RecursiveConversionsVisitor(BaseRecursiveConversionsVisitor[Conv, Result]):
    def visit_not_recursive(self, tp: AnyType) -> Result:
        return super().visit(tp)

    def visit(self, tp: AnyType) -> Result:
        recursive_type = is_recursive_type(
            tp, self.base_conversion_visitor, self._conversion, self.default_conversion
        )
        return super().visit(tp) if recursive_type else self.visit_not_recursive(tp)
