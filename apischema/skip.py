__all__ = ["NotNull", "Skip"]
from typing import Any, Iterator, Sequence, TypeVar, Union

from apischema.types import AnyType
from apischema.utils import UndefinedType
from apischema.visitor import Unsupported, Visitor


class Skipped(Exception):
    pass


class _Skip:
    def __call__(self, *, schema_only: bool):
        return SkipSchema if schema_only else self


Skip = _Skip()
SkipSchema = object()

T = TypeVar("T")
try:
    from typing import Annotated  # type: ignore
except ImportError:
    try:
        from typing_extensions import Annotated  # type: ignore
    except ImportError:
        Annotated = None  # type: ignore

if Annotated is not None:
    NotNull = Union[T, Annotated[None, Skip]]
else:

    class _NotNull:
        def __getitem__(self, item):
            raise TypeError("NotNull requires Annotated (PEP 593)")

    NotNull = _NotNull()  # type: ignore


class SkipVisitor(Visitor[Iterator[AnyType]]):
    def __init__(self, schema_only: bool):
        super().__init__()
        self.schema_only = schema_only

    def annotated(self, cls: AnyType, annotations: Sequence[Any]) -> Iterator[AnyType]:
        for annotation in annotations:
            if annotation is Skip or (self.schema_only and annotation is SkipSchema):
                raise Skipped
        return super().annotated(cls, annotations)

    def union(self, alternatives: Sequence[AnyType]) -> Iterator[AnyType]:
        for alt in alternatives:
            try:
                self.visit(alt)
            except Skipped:
                pass
            except (NotImplementedError, Unsupported):
                yield alt
            else:
                raise NotImplementedError()

    def visit(self, cls: AnyType) -> Iterator[AnyType]:
        if cls is UndefinedType:
            raise Skipped
        return super().visit(cls)


def filter_skipped(
    alternatives: Sequence[AnyType], *, schema_only=False
) -> Iterator[AnyType]:
    return SkipVisitor(schema_only).union(alternatives)
