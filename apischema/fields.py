from dataclasses import (Field, MISSING, _FIELDS,  # type: ignore
                         _FIELD_CLASSVAR, fields, is_dataclass)
from functools import wraps
from inspect import signature
from typing import (AbstractSet, Any, Iterable, Type,
                    TypeVar, cast, overload)

from apischema.utils import PREFIX


class NoDefault(Exception):
    pass


def has_default(field: Field) -> bool:
    return (field.default_factory is not MISSING  # type: ignore
            or field.default is not MISSING)


def get_default(field: Field) -> Any:
    if field.default_factory is not MISSING:  # type: ignore
        return field.default_factory()  # type: ignore
    if field.default is not MISSING:
        return field.default
    raise NoDefault()


FIELDS_SET_ATTR = f"{PREFIX}fields_set"

Cls = TypeVar("Cls", bound=Type)


@overload
def with_fields_set(cls: Cls) -> Cls:
    ...


@overload
def with_fields_set(init: bool) -> Cls:
    ...


def with_fields_set(arg=None, init=True):
    if arg is None:
        return lambda cls: with_fields_set(cls, init)
    cls = arg
    old_init = cls.__init__
    old_setattr = cls.__setattr__
    params = list(signature(old_init).parameters)

    if init:
        @wraps(old_init)
        def new_init(self, *args, **kwargs):
            self.__dict__[FIELDS_SET_ATTR] = set()
            old_init(self, *args, **kwargs)
            self.__dict__[FIELDS_SET_ATTR] = {*params[1:len(args) + 1],
                                              *kwargs}
    else:
        @wraps(old_init)
        def new_init(self, *args, **kwargs):
            self.__dict__[FIELDS_SET_ATTR] = set()
            old_init(self, *args, **kwargs)

    @wraps(old_setattr)
    def new_setattr(self, attr, value):
        self.__dict__[FIELDS_SET_ATTR].add(attr)
        old_setattr(self, attr, value)

    cls.__init__ = new_init
    cls.__setattr__ = new_setattr
    return cls


T = TypeVar("T")


def mark_set_fields(obj: T, *fields: str, overwrite=False) -> T:
    if overwrite:
        obj.__dict__[FIELDS_SET_ATTR] = set(fields)
    else:
        try:
            obj.__dict__[FIELDS_SET_ATTR].update(fields)
        except KeyError:
            fs = fields_set(obj)
            if any(f not in fs for f in fields):
                obj.__dict__[FIELDS_SET_ATTR] = {*fs, *fields}
    return obj


def unmark_set_fields(obj: T, *fields: str) -> T:
    if FIELDS_SET_ATTR in obj.__dict__:
        obj.__dict__[FIELDS_SET_ATTR].difference_update(fields)
    else:
        obj.__dict__[FIELDS_SET_ATTR] = set(fields_set(obj)).difference(fields)
    return obj


def fields_set(obj: Any) -> AbstractSet[str]:
    try:
        return getattr(obj, FIELDS_SET_ATTR)
    except AttributeError:
        if not is_dataclass(obj):
            raise TypeError("`fields_set` can only be called on dataclasses"
                            " and classes decorated with `with_fields_set`")
        return {f.name for f in fields(obj)}


def init_fields(cls: Type) -> Iterable[Field]:
    assert is_dataclass(cls)
    for field in getattr(cls, _FIELDS).values():
        if field.init and field._field_type != _FIELD_CLASSVAR:
            yield field


class FieldGetter:
    def __init__(self, obj):
        assert is_dataclass(obj)
        self.obj = obj
        self.fields = {f.name: f for f in fields(obj)}

    def __getattribute__(self, attr) -> Field:
        try:
            return super().__getattribute__("fields")[attr]
        except KeyError:
            cls = type(super().__getattribute__("obj")).__name__
            raise AttributeError(f"Class {cls} has no field 'attr'")


def get_fields(obj: T) -> T:
    return cast(T, FieldGetter(obj))
