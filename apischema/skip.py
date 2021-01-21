__all__ = ["NotNull", "Skip"]
from typing import Iterator, Sequence, TypeVar, Union

from apischema.types import AnyType
from apischema.typing import get_args, get_origin
from apischema.utils import UndefinedType


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


def is_skipped(tp: AnyType, *, schema_only) -> bool:
    return tp is UndefinedType or (
        get_origin(tp) is Annotated
        and (
            Skip in get_args(tp)[1:] or (schema_only and SkipSchema in get_args(tp)[1:])
        )
    )


def filter_skipped(
    alternatives: Sequence[AnyType], *, schema_only=False
) -> Iterator[AnyType]:
    return (alt for alt in alternatives if not is_skipped(alt, schema_only=schema_only))
