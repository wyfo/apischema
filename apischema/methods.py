import inspect
from functools import wraps
from inspect import signature
from types import FunctionType
from typing import Callable, Generic, Optional, Type, Union, cast

from apischema.typing import get_type_hints
from apischema.utils import PREFIX, T, get_origin_or_type2

MethodOrProperty = Union[Callable, property]


def _method_location(method: MethodOrProperty) -> Optional[Type]:
    if isinstance(method, property):
        assert method.fget is not None
        method = method.fget
    while hasattr(method, "__wrapped__"):
        method = method.__wrapped__  # type: ignore
    assert isinstance(method, FunctionType)
    global_name, *class_path = method.__qualname__.split(".")[:-1]
    if global_name not in method.__globals__:
        return None
    location = method.__globals__[global_name]
    for attr in class_path:
        if hasattr(location, attr):
            location = getattr(location, attr)
        else:
            break
    return location


def is_method(method: MethodOrProperty) -> bool:
    """Return if the function is method/property declared in a class"""
    return (
        isinstance(method, property)
        and method.fget is not None
        and is_method(method.fget)
    ) or (
        isinstance(method, FunctionType)
        and method.__name__ != method.__qualname__
        and isinstance(_method_location(method), (type, type(None)))
        and next(iter(inspect.signature(method).parameters), None) == "self"
    )


def method_class(method: MethodOrProperty) -> Optional[Type]:
    cls = _method_location(method)
    return cls if isinstance(cls, type) else None


METHOD_WRAPPER_ATTR = f"{PREFIX}method_wrapper"


def method_wrapper(method: MethodOrProperty, name: str = None) -> Callable:
    if isinstance(method, property):
        assert method.fget is not None
        name = name or method.fget.__name__

        @wraps(method.fget)
        def wrapper(self):
            return getattr(self, name)

    else:
        if hasattr(method, METHOD_WRAPPER_ATTR):
            return method
        name = name or method.__name__

        if list(signature(method).parameters) == ["self"]:

            @wraps(method)
            def wrapper(self):
                return getattr(self, name)()

        else:

            @wraps(method)
            def wrapper(self, *args, **kwargs):
                return getattr(self, name)(*args, **kwargs)

    setattr(wrapper, METHOD_WRAPPER_ATTR, True)
    return wrapper


class MethodWrapper(Generic[T]):
    def __init__(self, method: T):
        self._method = method

    def getter(self, func):
        self._method = self._method.getter(func)
        return self

    def setter(self, func):
        self._method = self._method.setter(func)
        return self

    def deleter(self, func):
        self._method = self._method.deleter(func)
        return self

    def __set_name__(self, owner, name):
        setattr(owner, name, self._method)

    def __call__(self, *args, **kwargs):
        raise RuntimeError("Method __set_name__ has not been called")


def method_registerer(
    arg: Optional[Callable],
    owner: Optional[Type],
    register: Callable[[Callable, Type, str], None],
):
    def decorator(method: MethodOrProperty):
        if owner is None and is_method(method) and method_class(method) is None:

            class Descriptor(MethodWrapper[MethodOrProperty]):
                def __set_name__(self, owner, name):
                    super().__set_name__(owner, name)
                    register(method_wrapper(method), owner, name)

            return Descriptor(method)
        else:
            owner2 = owner
            if is_method(method):
                if owner2 is None:
                    owner2 = method_class(method)
                method = method_wrapper(method)
            if owner2 is None:
                try:
                    hints = get_type_hints(method)
                    owner2 = get_origin_or_type2(hints[next(iter(hints))])
                except (KeyError, StopIteration):
                    raise TypeError("First parameter of method must be typed") from None
            assert not isinstance(method, property)
            register(cast(Callable, method), owner2, method.__name__)
            return method

    return decorator if arg is None else decorator(arg)
