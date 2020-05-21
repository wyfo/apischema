from dataclasses import Field, _FIELDS, _FIELD_CLASSVAR, dataclass  # type: ignore
from functools import partial
from types import FunctionType, MethodType
from typing import Any, Callable, Mapping, Optional, Type

from apischema.fields import FIELDS_SET_ATTR, get_default

MOCK_FIELDS_FIELD = "__mock_fields__"
MOCK_CLS_FIELD = "__mock_cls__"


class NonTrivialDependency(Exception):
    def __init__(self, attr: str):
        self.attr = attr
        self.validator: Optional[Callable] = None


@dataclass
class ValidatorMock:
    def __init__(
        self, cls: Type, fields: Mapping[str, Any], defaults: Mapping[str, Field]
    ):
        self.cls = cls
        self.fields = fields
        self.defaults = defaults
        setattr(self, FIELDS_SET_ATTR, set(fields))

    def __getattribute__(self, attr: str) -> Any:
        fields = super().__getattribute__("fields")
        if attr in fields:
            return fields[attr]
        defaults = super().__getattribute__("defaults")
        if attr in defaults:
            return get_default(defaults[attr])
        cls = super().__getattribute__("cls")
        if attr == "__class__":
            return cls
        if attr == "__dict__":
            return {
                **fields,
                **{name: get_default(field) for name, field in defaults.items()},
                FIELDS_SET_ATTR: set(fields),
            }
        if hasattr(cls, attr):
            member = getattr(cls, attr)
            # for classmethod (staticmethod are not handled)
            if isinstance(member, MethodType):
                return member
            if isinstance(member, FunctionType):
                return partial(member, self)
            if isinstance(member, property):
                return member.fget(self)  # type: ignore
            if all(
                f.name != attr or f._field_type == _FIELD_CLASSVAR
                for f in getattr(cls, _FIELDS).values()
            ):
                return member
        raise NonTrivialDependency(attr)
