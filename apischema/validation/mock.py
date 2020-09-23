from dataclasses import MISSING, dataclass
from functools import partial
from types import FunctionType, MethodType
from typing import Any, Mapping, Optional, TYPE_CHECKING, Type, TypeVar

from apischema.dataclasses import fields_items
from apischema.fields import FIELDS_SET_ATTR
from apischema.utils import get_default

if TYPE_CHECKING:
    from apischema.validation.validator import Validator

MOCK_FIELDS_FIELD = "__mock_fields__"
MOCK_CLS_FIELD = "__mock_cls__"


class NonTrivialDependency(Exception):
    def __init__(self, attr: str):
        self.attr = attr
        self.validator: Optional["Validator"] = None


@dataclass
class ValidatorMock:
    def __init__(self, cls: Type, fields: Mapping[str, Any]):
        self.cls = cls
        self.fields = fields
        setattr(self, FIELDS_SET_ATTR, set(fields))

    def __getattribute__(self, name: str) -> Any:
        fields = super().__getattribute__("fields")
        if name in fields:
            return fields[name]
        cls = super().__getattribute__("cls")
        cls_fields = fields_items(cls)
        if name in cls_fields:
            try:
                return get_default(cls_fields[name])
            except NotImplementedError:
                raise NonTrivialDependency(name) from None
        if name == "__class__":
            return cls
        if name == "__dict__":
            return {
                **fields,
                **{
                    name: get_default(field)
                    for name, field in cls_fields.items()
                    if field.default is not MISSING
                    or field.default_factory is not MISSING  # type: ignore
                },
                FIELDS_SET_ATTR: set(fields),
            }
        if name == FIELDS_SET_ATTR:
            return set(fields)
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
