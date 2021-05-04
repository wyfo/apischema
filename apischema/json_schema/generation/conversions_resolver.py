from typing import (
    Any,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
)

from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.types import AnyType
from apischema.visitor import Unsupported

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore


def merge_results(
    results: Iterable[Sequence[AnyType]], origin: AnyType
) -> Sequence[AnyType]:
    def rec(index=0) -> Iterator[Sequence[AnyType]]:
        if index < len(result_list):
            for next_ in rec(index + 1):
                for res in result_list[index]:
                    yield (res, *next_)
        else:
            yield ()

    result_list = list(results)
    return [origin[tuple(r)] for r in rec()]


class ConversionsResolver(ConversionsVisitor[Conv, Sequence[AnyType]]):
    def __init__(self):
        super().__init__()
        self._skip_after_conversion: bool = True
        self._rec_guard: Set[Tuple[AnyType, Conv]] = set()

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Sequence[AnyType]:
        return [Annotated[(res, *annotations)] for res in self.visit(tp)]

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Sequence[AnyType]:
        return merge_results([self.visit(value_type)], Collection)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Sequence[AnyType]:
        return merge_results([self.visit(key_type), self.visit(value_type)], Mapping)

    def tuple(self, types: Sequence[AnyType]) -> Sequence[AnyType]:
        return merge_results(map(self.visit, types), Tuple)

    def _union_result(self, results: Iterable[Sequence[AnyType]]) -> Sequence[AnyType]:
        return merge_results(results, Union)

    def _visit_not_conversion(self, tp: AnyType, dynamic: bool) -> Sequence[AnyType]:
        self._skip_after_conversion = False
        try:
            return super()._visit_not_conversion(tp, dynamic)
        except (NotImplementedError, Unsupported):
            return [] if dynamic else [tp]

    def _visit_conversion(
        self, tp: AnyType, conversion: Conv, dynamic: bool
    ) -> Sequence[AnyType]:
        if self._skip_after_conversion:
            return [] if dynamic else [tp]
        if (tp, conversion) not in self._rec_guard:
            self._rec_guard.add((tp, conversion))
            try:
                results = super()._visit_conversion(tp, conversion, dynamic)
            finally:
                self._rec_guard.remove((tp, conversion))
        else:
            results = []
        return results if dynamic else [tp, *results]


class WithConversionsResolver:
    def resolve_conversions(self, tp: AnyType) -> Sequence[AnyType]:
        raise NotImplementedError

    def __init_subclass__(cls, **kwargs):
        resolver: Type[ConversionsResolver]
        if issubclass(cls, DeserializationVisitor):

            class Resolver(ConversionsResolver, DeserializationVisitor):
                pass

        elif issubclass(cls, SerializationVisitor):

            class Resolver(ConversionsResolver, SerializationVisitor):
                pass

        else:
            return

        def resolve_conversions(
            self: ConversionsVisitor, tp: AnyType
        ) -> Sequence[AnyType]:
            return Resolver().visit_with_conversions(tp, self._conversions)

        assert issubclass(cls, WithConversionsResolver)
        cls.resolve_conversions = resolve_conversions  # type: ignore
