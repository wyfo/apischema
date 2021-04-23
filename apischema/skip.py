__all__ = ["NotNull", "Skip"]
from typing import TypeVar, Union

from apischema.types import AnyType
from apischema.typing import get_args, get_origin


class Skipped(Exception):
    pass


Skip = object()

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


def is_skipped(tp: AnyType) -> bool:
    return get_origin(tp) is Annotated and (Skip in get_args(tp)[1:])
