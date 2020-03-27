from dataclasses import Field, dataclass
from functools import partial
from types import FunctionType, MethodType
from typing import Any, Callable, ClassVar, Mapping, Optional, Type

from apischema.fields import FIELDS_SET_ATTR, get_default
from apischema.typing import get_type_hints

MOCK_FIELDS_FIELD = "__mock_fields__"
MOCK_CLS_FIELD = "__mock_cls__"


class NonTrivialDependency(Exception):
    def __init__(self, attr: str):
        self.attr = attr
        self.validator: Optional[Callable] = None


@dataclass
class ValidatorMock:
    def __init__(self, cls: Type, fields: Mapping[str, Any],
                 defaults: Mapping[str, Field]):
        self.cls = cls
        self.fields = fields
        self.defaults = defaults
        setattr(self, FIELDS_SET_ATTR, set(fields))

    def __getattribute__(self, attr: str) -> Any:
        if attr in super().__getattribute__("fields"):
            return super().__getattribute__("fields")[attr]
        if attr in super().__getattribute__("defaults"):
            return get_default(super().__getattribute__("defaults")[attr])
        if attr == "__class__":
            return super().__getattribute__("cls")
        if attr == "__dict__":
            return {**super().__getattribute__("fields"),
                    **{name: get_default(field)
                       for name, field
                       in super().__getattribute__("defaults").items()},
                    FIELDS_SET_ATTR: set(super().__getattribute__("fields"))}
        if hasattr(super().__getattribute__("cls"), attr):
            member = getattr(super().__getattribute__("cls"), attr)
            # for classmethod (staticmethod are not handled)
            if isinstance(member, MethodType):
                return member
            if isinstance(member, FunctionType):
                return partial(member, self)
            if isinstance(member, property):
                return member.fget(self)  # type: ignore
            types = get_type_hints(super().__getattribute__("cls"))
            if getattr(types.get(attr), "__origin__",
                       types.get(attr)) is ClassVar:
                return member
        raise NonTrivialDependency(attr)
