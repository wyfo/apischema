__all__ = ["fields_set", "is_set", "set_fields", "unset_fields", "with_fields_set"]
from dataclasses import (  # type: ignore
    Field,
    _FIELD,
    _FIELDS,
    _FIELD_INITVAR,
    is_dataclass,
)
from functools import wraps
from inspect import signature
from typing import AbstractSet, Any, Collection, Set, Type, TypeVar, cast

from apischema.objects.fields import get_field_name
from apischema.objects.getters import object_fields2
from apischema.utils import PREFIX

FIELDS_SET_ATTR = f"{PREFIX}fields_set"
_ALREADY_SET = f"{PREFIX}already_set"

Cls = TypeVar("Cls", bound=Type)


def with_fields_set(cls: Cls) -> Cls:
    from apischema.metadata.keys import DEFAULT_AS_SET_METADATA

    init_fields = set()
    post_init_fields = set()
    if is_dataclass(cls):
        for field in getattr(cls, _FIELDS).values():
            assert isinstance(field, Field)
            if field._field_type == _FIELD_INITVAR:  # type: ignore
                init_fields.add(field.name)
            if field._field_type == _FIELD and not field.init:  # type: ignore
                post_init_fields.add(field.name)
            if field.metadata.get(DEFAULT_AS_SET_METADATA):
                post_init_fields.add(field.name)
    params = list(signature(cls.__init__).parameters)[1:]
    old_new = cls.__new__
    old_init = cls.__init__
    old_setattr = cls.__setattr__

    def new_new(*args, **kwargs):
        if old_new is object.__new__:
            obj = object.__new__(args[0])
        else:
            obj = old_new(*args, **kwargs)
        # Initialize FIELD_SET_ATTR in order to prevent inherited class which override
        # __init__ to raise in __setattr__
        obj.__dict__[FIELDS_SET_ATTR] = set()
        return obj

    def new_init(self, *args, **kwargs):
        prev_fields_set = self.__dict__.get(FIELDS_SET_ATTR, set()).copy()
        self.__dict__[FIELDS_SET_ATTR] = set()
        try:
            old_init(self, *args, **kwargs)
        except TypeError as err:
            if str(err) == no_dataclass_init_error:
                raise RuntimeError(dataclass_before_error) from None
            else:
                raise
        arg_fields = {*params[: len(args)], *kwargs} - init_fields
        self.__dict__[FIELDS_SET_ATTR] = prev_fields_set | arg_fields | post_init_fields

    def new_setattr(self, attr, value):
        try:
            self.__dict__[FIELDS_SET_ATTR].add(attr)
        except KeyError:
            raise RuntimeError(dataclass_before_error) from None
        old_setattr(self, attr, value)

    for attr, old, new in [
        ("__new__", old_new, new_new),
        ("__init__", old_init, new_init),
        ("__setattr__", old_setattr, new_setattr),
    ]:
        if hasattr(old, _ALREADY_SET):
            continue
        setattr(new, _ALREADY_SET, True)
        setattr(cls, attr, wraps(old)(new))  # type: ignore

    return cls


no_dataclass_init_error = (
    "object.__init__() takes exactly one argument (the instance to initialize)"
)
dataclass_before_error = (
    f"{with_fields_set.__name__} must be put before dataclass decorator"
)


T = TypeVar("T")


def _field_names(fields: Collection) -> AbstractSet[str]:
    result: Set[str] = set()
    for field in fields:
        result.add(get_field_name(field))
    return result


def _fields_set(obj: Any) -> Set[str]:
    if not hasattr(obj, FIELDS_SET_ATTR):
        try:
            default_fields: Collection[str] = object_fields2(obj)
        except TypeError:
            default_fields = ()
        try:
            setattr(obj, FIELDS_SET_ATTR, set(default_fields))
        except AttributeError:  # cannot setattr (builtin, etc.)
            raise TypeError(f"Cannot track fields set on {obj}")
    return getattr(obj, FIELDS_SET_ATTR)


def set_fields(obj: T, *fields: Any, overwrite=False) -> T:
    if overwrite:
        _fields_set(obj).clear()
    _fields_set(obj).update(map(get_field_name, fields))
    return obj


def unset_fields(obj: T, *fields: Any) -> T:
    _fields_set(obj).difference_update(map(get_field_name, fields))
    return obj


# This could just be an alias with a specified type, but it's better handled by IDE
# like this
def fields_set(obj: Any) -> AbstractSet[str]:
    return _fields_set(obj)


class FieldIsSet:
    def __init__(self, obj: Any):
        self.fields_set = fields_set(obj)

    def __getattribute__(self, name: str) -> bool:
        return name in object.__getattribute__(self, "fields_set")


def is_set(obj: T) -> T:
    return cast(T, FieldIsSet(obj))
