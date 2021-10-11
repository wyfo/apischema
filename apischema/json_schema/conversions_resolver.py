from contextlib import suppress
from typing import (
    Any,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
)

from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.types import AnyType
from apischema.utils import is_hashable
from apischema.visitor import Unsupported

try:
    from apischema.typing import Annotated, is_union
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
    return [(Union if is_union(origin) else origin)[tuple(r)] for r in rec()]


class ConversionsResolver(ConversionsVisitor[Conv, Sequence[AnyType]]):
    def __init__(self, default_conversion: DefaultConversion):
        super().__init__(default_conversion)
        self._skip_conversion = True
        self._rec_guard: Set[Tuple[AnyType, Conv]] = set()

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Sequence[AnyType]:
        return [
            Annotated[(res, *annotations)] for res in super().annotated(tp, annotations)
        ]

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Sequence[AnyType]:
        return merge_results([self.visit(value_type)], Collection)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Sequence[AnyType]:
        return merge_results([self.visit(key_type), self.visit(value_type)], Mapping)

    def new_type(self, tp: AnyType, super_type: AnyType) -> Sequence[AnyType]:
        raise NotImplementedError

    def tuple(self, types: Sequence[AnyType]) -> Sequence[AnyType]:
        return merge_results(map(self.visit, types), Tuple)

    def _visited_union(self, results: Sequence[Sequence[AnyType]]) -> Sequence[AnyType]:
        return merge_results(results, Union)

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Any,
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> Sequence[AnyType]:
        if conversion is not None and self._skip_conversion:
            return [] if dynamic else [tp]
        self._skip_conversion = False
        results: Sequence[AnyType] = []
        if not is_hashable(tp):
            with suppress(NotImplementedError, Unsupported):
                results = super().visit_conversion(
                    tp, conversion, dynamic, next_conversion
                )
        elif (tp, conversion) not in self._rec_guard:
            self._rec_guard.add((tp, conversion))
            with suppress(NotImplementedError, Unsupported):
                results = super().visit_conversion(
                    tp, conversion, dynamic, next_conversion
                )
            self._rec_guard.remove((tp, conversion))
        if not dynamic and (conversion is not None or not results):
            results = [tp, *results]
        return results


class WithConversionsResolver:
    def resolve_conversion(self, tp: AnyType) -> Sequence[AnyType]:
        raise NotImplementedError

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Resolver: Type[ConversionsResolver]
        if issubclass(cls, DeserializationVisitor):

            class Resolver(ConversionsResolver, DeserializationVisitor):
                pass

        elif issubclass(cls, SerializationVisitor):

            class Resolver(ConversionsResolver, SerializationVisitor):
                pass

        else:
            return

        def resolve_conversion(
            self: ConversionsVisitor, tp: AnyType
        ) -> Sequence[AnyType]:
            return Resolver(self.default_conversion).visit_with_conv(
                tp, self._conversion
            )

        assert issubclass(cls, WithConversionsResolver)
        cls.resolve_conversion = resolve_conversion  # type: ignore
