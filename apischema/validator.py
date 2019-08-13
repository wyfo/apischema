from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from functools import partial
from inspect import getmembers, isroutine
from types import FunctionType
from typing import (Any, Callable, ClassVar, Collection, Dict, Iterable, Tuple,
                    Type, TypeVar, Union, overload)

MOCK_FIELDS_FIELD = "__mock_fields__"
MOCK_CLS_FIELD = "__mock_cls__"

Path = Tuple[str, ...]
ErrorMsg = str
Error = Union[ErrorMsg, Tuple[Union[str, Path], ErrorMsg]]
ValidationResult = Iterable[Error]


class ValidatorMock:
    def __init__(self, fields: Dict[str, Any], cls: Type):
        setattr(self, MOCK_FIELDS_FIELD, fields)
        setattr(self, MOCK_CLS_FIELD, cls)

    def __getattr__(self, item: str) -> Any:
        if item in getattr(self, MOCK_FIELDS_FIELD):
            return getattr(self, MOCK_FIELDS_FIELD)[item]
        if hasattr(getattr(self, MOCK_CLS_FIELD), item):
            member = getattr(getattr(self, MOCK_CLS_FIELD), item)
            if isroutine(member):
                return partial(member, self)
            raise NotImplementedError()
        raise AttributeError(f"attribute {item} not initialized")


@dataclass
class Validator(ABC):
    FIELD: ClassVar[str] = "__validators__"
    func: Callable[..., ValidationResult]

    def __call__(self, this: Any) -> ValidationResult:
        yield from self.func(this)


@dataclass
class PartialValidator(Validator):
    FIELD: ClassVar[str] = "__partial_validators__"
    dependencies: Collection[str]

    def can_be_called(self, fields: Iterable[str]):
        for dep in self.dependencies:
            if dep not in fields:
                return False
        return True


V = TypeVar("V", bound=Validator)


# Mypy workaround (see https://github.com/python/mypy/issues/3737)
@overload
def validators(cls: Type, val_cls: Type[V]) -> Iterable[V]:
    ...


@overload
def validators(cls: Type) -> Iterable[Validator]:
    ...


def validators(cls, val_cls=Validator):
    if hasattr(cls, val_cls.FIELD):
        return getattr(cls, val_cls.FIELD)
    members = getmembers(cls, lambda m: type(m) == val_cls)
    res = [val for _, val in members]
    setattr(cls, val_cls.FIELD, res)
    return res


@overload
def validate(func: Callable[..., ValidationResult]) -> Validator:
    ...


@overload
def validate(*dependencies: str) -> Callable[
    [Callable[..., ValidationResult]], PartialValidator
]:
    ...


def validate(*args):
    if isinstance(args[0], FunctionType):
        return Validator(args[0])
    else:
        return lambda f: PartialValidator(f, args)
