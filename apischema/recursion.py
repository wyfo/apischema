from enum import Enum
from typing import (
    Any,
    Collection,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
)

from apischema.cache import cache
from apischema.conversions import AnyConversion
from apischema.conversions.conversions import DefaultConversion
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.objects import ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.types import AnyType
from apischema.utils import Lazy
from apischema.visitor import Result

RecursionKey = Tuple[AnyType, Optional[AnyConversion]]


class RecursiveChecker(ConversionsVisitor[Conv, Any], ObjectVisitor[Any]):
    def __init__(self, default_conversion: DefaultConversion):
        super().__init__(default_conversion)
        self._cache = recursion_cache(self.__class__)
        self._recursive: Dict[RecursionKey, Set[RecursionKey]] = {}
        self._all_recursive: Set[RecursionKey] = set()
        self._guard: List[RecursionKey] = []
        self._guard_indices: Dict[RecursionKey, int] = {}

    def any(self):
        pass

    def collection(self, cls: Type[Collection], value_type: AnyType):
        return self.visit(value_type)

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
        for tp in types:
            self.visit(tp)

    def _visited_union(self, results: Sequence):
        pass

    def unsupported(self, tp: AnyType):
        pass

    def visit(self, tp: AnyType):
        rec_key = (tp, self._conversion)
        if rec_key in self._cache:
            pass
        elif rec_key in self._guard_indices:
            recursive = self._guard[self._guard_indices[rec_key] :]
            self._recursive.setdefault(rec_key, set()).update(recursive)
            self._all_recursive.update(recursive)
        else:
            self._guard_indices[rec_key] = len(self._guard)
            self._guard.append(rec_key)
            try:
                super().visit(tp)
            finally:
                self._guard.pop()
                self._guard_indices.pop(rec_key)
            if rec_key in self._recursive:
                for key in self._recursive[rec_key]:
                    self._cache[key] = True
                assert self._cache[rec_key]
            elif rec_key not in self._all_recursive:
                self._cache[rec_key] = False


class DeserializationRecursiveChecker(
    DeserializationVisitor,
    DeserializationObjectVisitor,
    RecursiveChecker[Deserialization],
):
    pass


class SerializationRecursiveChecker(
    SerializationVisitor, SerializationObjectVisitor, RecursiveChecker[Serialization]
):
    pass


@cache  # use @cache for reset
def recursion_cache(checker_cls: Type[RecursiveChecker]) -> Dict[RecursionKey, bool]:
    return {}


@cache
def is_recursive(
    tp: AnyType,
    conversion: Optional[AnyConversion],
    default_conversion: DefaultConversion,
    checker_cls: Type[RecursiveChecker],
) -> bool:
    cache, rec_key = recursion_cache(checker_cls), (tp, conversion)
    if rec_key not in cache:
        checker_cls(default_conversion).visit_with_conv(tp, conversion)
    return cache[rec_key]


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
        if is_recursive(
            tp,
            self._conversion,
            self.default_conversion,
            DeserializationRecursiveChecker  # type: ignore
            if isinstance(self, DeserializationVisitor)
            else SerializationRecursiveChecker,
            # None,
        ):
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
