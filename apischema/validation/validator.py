from dataclasses import Field
from functools import wraps
from inspect import Parameter, isfunction, isgeneratorfunction, signature
from types import MethodType
from typing import (AbstractSet, Any, Callable, Iterable,
                    Iterator,
                    Sequence,
                    TypeVar, overload)

from apischema.types import DictWithUnion, Metadata
from apischema.utils import PREFIX, to_generator
from apischema.validation.dependencies import find_end_dependencies
from apischema.validation.errors import (Error, ValidationError,
                                         build_from_errors, exception)
from apischema.validation.mock import NonTrivialDependency

T = TypeVar("T", contravariant=True)


# use attribute instead of global dict in order to be inherited
VALIDATORS_ATTR = f"{PREFIX}validators"
ValidatorResult = Iterator[Error]


class Validator:
    def __init__(self, func: Callable):
        wraps(func)(self)
        self.func = func
        if not isgeneratorfunction(func):
            self.validate = to_generator(func)
        else:
            self.validate = func

    def __get__(self, instance, owner):
        return self if instance is None else MethodType(self.func, instance)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __set_name__(self, owner, name: str):
        parameters = signature(self.func).parameters
        if not any(param.kind == Parameter.VAR_KEYWORD
                   for param in parameters.values()):
            params = set(parameters) - {"self"}
            wrapped = self.validate

            def wrapper(self: T, **kwargs):
                kwargs2 = {k: v for k, v in kwargs.items() if k in params}
                return wrapped(self, **kwargs2)

            self.validate = wrapper
        self.owner = owner
        self.dependencies = find_end_dependencies(owner, self.func)
        setattr(owner, VALIDATORS_ATTR, (*get_validators(owner), self))

    def can_be_called(self, fields: AbstractSet[str]) -> bool:
        return all(dep in fields for dep in self.dependencies)


def get_validators(obj) -> Sequence[Validator]:
    return getattr(obj, VALIDATORS_ATTR, ())


class Discard(Exception):
    def __init__(self, *fields):
        if not all(isinstance(f, Field) for f in fields):
            raise TypeError("Only fields can be discarded")
        self.fields: AbstractSet[str] = {f.name for f in fields}


def validate(_obj: T, _validators: Sequence[Validator] = None, **kwargs):
    if _validators is None:
        _validators = get_validators(_obj)
    if kwargs is None:
        kwargs = {}
    errors = []
    while True:
        for i, validator in enumerate(_validators):
            try:
                errors.extend(validator.validate(_obj, **kwargs))
            except ValidationError:
                raise
            except Discard as err:
                _validators = [v for v in _validators[i + 1:]
                               if not v.dependencies & err.fields]
                break
            except NonTrivialDependency as exc:
                exc.validator = validator
                raise
            except Exception as err:
                errors.append(exception(err))
        else:
            break
    if errors:
        raise build_from_errors(errors)


V = TypeVar("V", bound=Callable)


@overload
def validator(func: V) -> V:
    ...


@overload
def validator(field: Any, *, discard: bool = True) -> Callable[[V], V]:
    ...


def validator(arg=None, field=None, *, discard=True):
    if isfunction(arg):
        return Validator(arg)
    if arg is None and field is None or arg is not None and field is not None:
        raise ValueError("Bad use of validator")
    field = field or arg
    if not isinstance(field, Field):
        raise TypeError("validator argument must be a field")

    def decorator(func):
        @wraps(func)
        def wrapper(self, **kwargs):
            has_error = False
            for error in func(self, **kwargs):
                has_error = True
                if isinstance(error, str):
                    yield field, error
                else:
                    path, msg = error
                    if isinstance(path, Iterable) and not isinstance(path, str):
                        yield (field, *path), msg
                    else:
                        yield (field, path), msg
            if has_error and discard:
                raise Discard(field)

        return validator(wrapper)

    return decorator


VALIDATORS_METADATA = f"{PREFIX}validators"


def field_validator(*validators: Callable) -> Metadata:
    return DictWithUnion({VALIDATORS_METADATA: validators})
