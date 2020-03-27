from typing import Any, Collection, Type

from apischema.typing import _type_repr
from apischema.validation.errors import ErrorMsg


def wrong_type(cls: Type, expected: Type) -> ErrorMsg:
    return f"expected type '{_type_repr(expected)}', got '{_type_repr(cls)}'"


def bad_literal(value: Any, values: Collection[Any]) -> ErrorMsg:
    return f"'{value}' is not one of {values}"
