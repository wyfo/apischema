__all__ = ["NotNull", "Skip"]
from typing import TypeVar, Union

from apischema.visitor import Unsupported

Skip = Unsupported

T = TypeVar("T")
try:
    from apischema.typing import Annotated

    NotNull = Union[T, Annotated[None, Skip]]
except ImportError:

    class _NotNull:
        def __getitem__(self, item):
            raise TypeError("NotNull requires Annotated (PEP 593)")

    NotNull = _NotNull()  # type: ignore
