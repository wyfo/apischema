from dataclasses import Field
from functools import wraps
from inspect import Parameter, isfunction, isgeneratorfunction, signature
from types import MethodType
from typing import (
    AbstractSet,
    Any,
    Callable,
    Iterable,
    Optional,
    Sequence,
    TypeVar,
    overload,
)

from apischema.types import AnyType, DictWithUnion, Metadata
from apischema.typing import NO_TYPE, Protocol
from apischema.utils import PREFIX
from apischema.validation.dependencies import find_all_dependencies
from apischema.validation.errors import (
    ValidationError,
    build_from_errors,
    exception,
    merge,
)
from apischema.validation.mock import NonTrivialDependency

if Protocol is not NO_TYPE:

    class ValidatorFunc(Protocol):
        @overload
        def __call__(self, _obj):
            ...

        @overload
        def __call__(self, _obj, **kwargs):
            ...

        def __call__(self, _obj, **kwargs):
            ...

    class BaseValidator(Protocol):
        @overload
        def validate(self, _obj):
            ...

        @overload
        def validate(self, _obj, **kwargs):
            ...

        def validate(self, _obj, **kwargs):
            ...


else:
    ValidatorFunc = Callable  # type: ignore
    BaseValidator = Callable  # type: ignore

# use attribute instead of global dict in order to be inherited
VALIDATORS_ATTR = f"{PREFIX}validators"


class SimpleValidator:
    def __init__(self, func: "ValidatorFunc"):
        self.func = func
        parameters = signature(func).parameters
        validate = func
        if not any(
            param.kind == Parameter.VAR_KEYWORD for param in parameters.values()
        ):
            if not parameters:
                raise TypeError("validator must have at least one parameter")
            params = set(list(parameters)[1:])
            wrapped = validate

            def validate(_obj, **kwargs):
                kwargs2 = {k: v for k, v in kwargs.items() if k in params}
                return wrapped(_obj, **kwargs2)

        if isgeneratorfunction(func):
            wrapped = validate

            def validate(_obj, **kwargs):
                errors = [*validate(_obj, **kwargs)]
                if errors:
                    raise build_from_errors(errors)

        self.validate = validate  # type: ignore

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def validate(self, _obj, **kwargs):  # for typing
        ...


class Validator(SimpleValidator):
    def __init__(self, func: Callable):
        if isgeneratorfunction(func):

            @wraps(func)
            def validate(_obj, **kwargs):
                errors = []
                try:
                    errors.extend(func(_obj, **kwargs))
                except ValidationError:
                    raise RuntimeError("Validation error raised in generator validator")
                except Discard as err:
                    err.error = build_from_errors(errors)
                    raise
                if errors:
                    raise build_from_errors(errors)

            validate.__annotations__.pop("return", ...)
            super().__init__(validate)
        else:
            super().__init__(func)
        wraps(func)(self)
        self.func = func

    def __get__(self, instance, owner):
        return self if instance is None else MethodType(self.func, instance)

    def __set_name__(self, owner, name: str):
        self.dependencies = find_all_dependencies(owner, self.func)
        setattr(owner, VALIDATORS_ATTR, (*get_validators(owner), self))

    def can_be_called(self, fields: AbstractSet[str]) -> bool:
        return all(dep in fields for dep in self.dependencies)


Func = TypeVar("Func", bound=Callable)


def get_validators(obj) -> Sequence[Validator]:
    return getattr(obj, VALIDATORS_ATTR, ())


def add_validator(cls: AnyType, *validators: ValidatorFunc):
    for func in validators:
        validator = SimpleValidator(func)
        setattr(cls, VALIDATORS_ATTR, (*get_validators(cls), validator))


class Discard(Exception):
    def __init__(self, *fields):
        if not all(isinstance(f, Field) for f in fields):
            raise TypeError("Only fields can be discarded")
        self.fields: AbstractSet[str] = {f.name for f in fields}
        self.error: Optional[ValidationError] = None


T = TypeVar("T")


def validate(_obj: T, _validators: Sequence[BaseValidator] = None, **kwargs) -> T:
    if _validators is None:
        _validators = get_validators(_obj)
    if not _validators:
        return _obj
    error: Optional[ValidationError] = None
    while True:
        for i, validator in enumerate(_validators):
            try:
                validator.validate(_obj, **kwargs)
            except ValidationError as err:
                error = merge(error, err)
            except Discard as err:
                if err.error is None:
                    raise RuntimeError("Discard can only be raised in class Validator")
                error = merge(error, err.error)
                _validators = [
                    v
                    for v in _validators[i + 1 :]
                    if not isinstance(v, Validator) or not v.dependencies & err.fields
                ]
                break
            except NonTrivialDependency as exc:
                assert isinstance(validator, Validator)
                exc.validator = validator
                raise
            except Exception as err:
                error = merge(error, ValidationError([exception(err)]))
        else:
            break
    if error is not None:
        raise error
    return _obj


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


def field_validator(*validators: ValidatorFunc) -> Metadata:
    return DictWithUnion({VALIDATORS_METADATA: list(map(SimpleValidator, validators))})
