__all__ = ["fields", "fields_set", "set_fields", "unset_fields", "with_fields_set"]
from dataclasses import (  # type: ignore
    Field,
    _FIELD,
    _FIELDS,
    _FIELD_CLASSVAR,
    _FIELD_INITVAR,
    fields as fields_,
    is_dataclass,
)
from functools import wraps
from inspect import signature
from typing import (
    AbstractSet,
    Any,
    Collection,
    Set,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.utils import PREFIX

FIELDS_SET_ATTR = f"{PREFIX}fields_set"


def _check_dataclass(obj):
    if not is_dataclass(obj):
        raise ValueError("not a dataclass")


Cls = TypeVar("Cls", bound=Type)

_ALREADY_SET = f"{PREFIX}already_set"


def with_fields_set(cls: Cls) -> Cls:
    from apischema.metadata.keys import DEFAULT_AS_SET

    init_fields = set()
    post_init_fields = set()
    if is_dataclass(cls):
        for field in getattr(cls, _FIELDS).values():
            assert isinstance(field, Field)
            if field._field_type == _FIELD_INITVAR:  # type: ignore
                init_fields.add(field.name)
            if field._field_type == _FIELD and not field.init:  # type: ignore
                post_init_fields.add(field.name)
            if field.metadata.get(DEFAULT_AS_SET):
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


def _all_fields(obj: Any) -> AbstractSet[str]:
    _check_dataclass(obj)
    return {
        f.name
        for f in fields_(obj)
        if f._field_type is not _FIELD_INITVAR  # type: ignore
    }


def _field_names(obj: Any, fields: Collection) -> AbstractSet[str]:
    all_fields = _all_fields(obj)
    result: Set[str] = set()
    for f in fields:
        if isinstance(f, Field):
            f = f.name
        if not isinstance(f, str):
            raise ValueError("Fields must be dataclass Field or str")
        if f not in all_fields:
            raise ValueError(f"Wrong field {f}")
        result.add(f)
    return result


def set_fields(obj: T, *fields: Any, overwrite=False) -> T:
    _fields = _field_names(obj, fields)
    if overwrite:
        obj.__dict__[FIELDS_SET_ATTR] = _fields
    else:
        try:
            obj.__dict__[FIELDS_SET_ATTR].update(_fields)
        except KeyError:
            # with_fields_set is not use, so all fields are set
            pass
    return obj


def unset_fields(obj: T, *fields: Any) -> T:
    _fields = _field_names(obj, fields)
    obj.__dict__[FIELDS_SET_ATTR] = fields_set(obj) - _fields
    return obj


def fields_set(obj: Any) -> AbstractSet[str]:
    try:
        return getattr(obj, FIELDS_SET_ATTR)
    except AttributeError:
        return _all_fields(obj)


class FieldGetter:
    def __init__(self, obj):
        _check_dataclass(obj)
        self.fields = {
            name: f
            for name, f in getattr(obj, _FIELDS).items()
            if not f._field_type == _FIELD_CLASSVAR
        }

    def __getattribute__(self, name: str) -> Field:
        try:
            return super().__getattribute__("fields")[name]
        except KeyError:
            raise AttributeError(name)


@overload
def fields(obj: Type[T]) -> T:
    ...


@overload
def fields(obj: T) -> T:
    ...


# Overload because of Mypy issue
# https://github.com/python/mypy/issues/9003#issuecomment-667418520
def fields(obj: Union[Type[T], T]) -> T:
    return cast(T, FieldGetter(obj))


class FieldIsSet(FieldGetter):
    def __init__(self, obj):
        super().__init__(obj)
        self.obj = obj

    def __getattribute__(self, name: str) -> bool:  # type: ignore
        field = super().__getattribute__(name)
        return field.name in fields_set(object.__getattribute__(self, "obj"))


def is_set(obj: T) -> T:
    return cast(T, FieldIsSet(obj))
