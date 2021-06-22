from dataclasses import dataclass
from functools import partial
from types import FunctionType, MethodType
from typing import Any, Mapping, Optional, TYPE_CHECKING, Type, TypeVar

from apischema.fields import FIELDS_SET_ATTR
from apischema.objects import object_fields

if TYPE_CHECKING:
    from apischema.validation.validators import Validator

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

    def __getattribute__(self, name: str) -> Any:
        values = super().__getattribute__("values")
        if name in values:
            return values[name]
        cls = super().__getattribute__("cls")
        fields = object_fields(cls, deserialization=True)
        if name in fields:
            if fields[name].required:
                raise NonTrivialDependency(name)
            return fields[name].get_default()
        if name == "__class__":
            return cls
        if name == "__dict__":
            return {**values, FIELDS_SET_ATTR: set(values)}
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
