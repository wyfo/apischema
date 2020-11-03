from dataclasses import dataclass, fields
from functools import partial
from types import FunctionType, MethodType
from typing import Any, Mapping, Optional, TYPE_CHECKING, Type, TypeVar

from apischema.dataclass_utils import get_default, has_default
from apischema.fields import FIELDS_SET_ATTR, set_fields

if TYPE_CHECKING:
    from apischema.validation.validator import Validator

MOCK_FIELDS_FIELD = "__mock_fields__"
MOCK_CLS_FIELD = "__mock_cls__"


class NonTrivialDependency(Exception):
    def __init__(self, attr: str):
        self.attr = attr
        self.validator: Optional["Validator"] = None


@dataclass(init=False)
class ValidatorMock:
    def __init__(self, cls: Type, values: Mapping[str, Any]):
        self.cls = cls
        self.values = values
        set_fields(self, *values, overwrite=True)

    def __getattribute__(self, name: str) -> Any:
        values = super().__getattribute__("values")
        if name in values:
            return values[name]
        cls = super().__getattribute__("cls")
        for field in fields(cls):
            if name == field.name:
                try:
                    return get_default(field)
                except NotImplementedError:
                    raise NonTrivialDependency(name) from None
        if name == "__class__":
            return cls
        if name == "__dict__":
            return {
                **values,
                **{
                    field.name: get_default(field)
                    for field in fields(cls)
                    if has_default(field)
                },
                FIELDS_SET_ATTR: set(values),
            }
        if name == FIELDS_SET_ATTR:
            return set(values)
        if hasattr(cls, name):
            member = getattr(cls, name)
            # for classmethod (staticmethod are not handled)
            if isinstance(member, MethodType):
                return member
            if isinstance(member, FunctionType):
                return partial(member, self)
            if isinstance(member, property):
                return member.fget(self)  # type: ignore
            return member
        raise NonTrivialDependency(name)


T = TypeVar("T")
