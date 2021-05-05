__all__ = ["NotNull", "Skip"]
from typing import TypeVar, Union

from apischema.types import AnyType
from apischema.typing import get_args, is_annotated


class Skipped(Exception):
    pass


Skip = object()

T = TypeVar("T")
try:
    from apischema.typing import Annotated

    NotNull = Union[T, Annotated[None, Skip]]
except ImportError:

    class _NotNull:
        def __getitem__(self, item):
            raise TypeError("NotNull requires Annotated (PEP 593)")

    NotNull = _NotNull()  # type: ignore


def is_skipped(tp: AnyType) -> bool:
    return is_annotated(tp) and (Skip in get_args(tp)[1:])
