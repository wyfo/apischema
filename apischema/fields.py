from dataclasses import (  # type: ignore
    Field,
    MISSING,
    _FIELD,
    _FIELDS,
    _FIELD_INITVAR,
    fields as fields_,
    is_dataclass,
)
from functools import wraps
from inspect import signature
from typing import AbstractSet, Any, Type, TypeVar, Union, cast

from apischema.utils import PREFIX


class NoDefault(Exception):
    pass


def get_default(field: Field) -> Any:
    if field.default_factory is not MISSING:  # type: ignore
        return field.default_factory()  # type: ignore
    if field.default is not MISSING:
        return field.default
    raise NoDefault()


FIELDS_SET_CACHE_ATTR = f"{PREFIX}fields_set_cache"

FIELDS_SET_ATTR = f"{PREFIX}fields_set"

Cls = TypeVar("Cls", bound=Type)


def check_dataclass(obj):
    if not is_dataclass(obj):
        raise ValueError("not a dataclass")


def with_fields_set(cls: Cls) -> Cls:
    check_dataclass(cls)
    init_fields = set()
    post_init_fields = set()
    for field in getattr(cls, _FIELDS).values():
        assert isinstance(field, Field)
        if field._field_type == _FIELD_INITVAR:  # type: ignore
            init_fields.add(field.name)
        if field._field_type == _FIELD and not field.init:  # type: ignore
            post_init_fields.add(field.name)
    params = list(signature(cls.__init__).parameters)
    old_new = cls.__new__
    old_init = cls.__init__
    old_setattr = cls.__setattr__

    @wraps(old_new)
    def new_new(*args, **kwargs):
        if old_new is object.__new__:
            obj = object.__new__(args[0])
        else:
            obj = old_new(*args, **kwargs)
        obj.__dict__[FIELDS_SET_ATTR] = set()
        return obj

    @wraps(old_init)
    def new_init(*args, **kwargs):
        args[0].__dict__[FIELDS_SET_ATTR] = set()
        old_init(*args, **kwargs)
        arg_fields = {*params[1 : len(args)], *kwargs} - init_fields
        args[0].__dict__[FIELDS_SET_ATTR] = arg_fields | post_init_fields

    @wraps(old_setattr)
    def new_setattr(self, attr, value):
        self.__dict__[FIELDS_SET_ATTR].add(attr)
        old_setattr(self, attr, value)

    cls.__new__ = new_new
    cls.__init__ = new_init
    cls.__setattr__ = new_setattr
    return cls


T = TypeVar("T")


def mark_set_fields(obj: T, *fields: str, overwrite=False) -> T:
    check_dataclass(obj)
    all_fields = {f.name for f in fields_(obj)}
    if any(f not in all_fields for f in fields):
        raise ValueError(f"{set(fields) - all_fields} are not fields")
    if overwrite:
        obj.__dict__[FIELDS_SET_ATTR] = set(fields)
    else:
        try:
            obj.__dict__[FIELDS_SET_ATTR].update(fields)
        except KeyError:
            fs = get_fields_set(obj)
            if any(f not in fs for f in fields):
                obj.__dict__[FIELDS_SET_ATTR] = {*fs, *fields}
    return obj


def unmark_set_fields(obj: T, *fields: str) -> T:
    check_dataclass(obj)
    if FIELDS_SET_ATTR in obj.__dict__:
        obj.__dict__[FIELDS_SET_ATTR].difference_update(fields)
    else:
        obj.__dict__[FIELDS_SET_ATTR] = set(get_fields_set(obj)).difference(fields)
    return obj


def get_fields_set(obj: Any) -> AbstractSet[str]:
    check_dataclass(obj)
    try:
        return getattr(obj, FIELDS_SET_ATTR)
    except AttributeError:
        return {f.name for f in fields_(obj)}


class FieldGetter:
    def __init__(self, obj):
        check_dataclass(obj)
        self.obj = obj
        self.fields = {f.name: f for f in fields_(obj)}

    def __getattribute__(self, attr) -> Field:
        try:
            return super().__getattribute__("fields")[attr]
        except KeyError:
            cls = type(super().__getattribute__("obj")).__name__
            raise AttributeError(f"Class {cls} has no field 'attr'")


def get_fields(obj: Union[Type[T], T]) -> T:
    return cast(T, FieldGetter(obj))
