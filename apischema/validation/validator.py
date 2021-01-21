from collections import defaultdict
from dataclasses import Field
from functools import wraps
from inspect import Parameter, isgeneratorfunction, signature
from types import MethodType
from typing import (
    AbstractSet,
    Any,
    Callable,
    Collection,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    overload,
)

from apischema.conversions.dataclass_models import get_model_origin, has_model_origin
from apischema.types import AnyType
from apischema.typing import get_type_hints
from apischema.utils import get_origin_or_type, is_method, method_class
from apischema.validation.dependencies import find_all_dependencies
from apischema.validation.errors import (
    Error,
    FieldPath,
    ValidationError,
    merge_errors,
    yield_to_raise,
)
from apischema.validation.mock import NonTrivialDependency

_validators: Dict[Type, List["Validator"]] = defaultdict(list)


def get_validators(tp: AnyType) -> Sequence["Validator"]:
    validators = []
    if hasattr(tp, "__mro__"):
        for sub_cls in tp.__mro__:
            validators.extend(_validators[sub_cls])
    else:
        validators.extend(_validators[tp])
    if has_model_origin(tp):
        validators.extend(get_validators(get_model_origin(tp)))
    return validators


class Discard(Exception):
    def __init__(self, fields: AbstractSet[Field], error: ValidationError):
        self.fields = fields
        self.error = error


class Validator:
    def __init__(
        self,
        func: Callable,
        field: Field = None,
        discard: Union[Field, Collection[Field]] = None,
    ):
        wraps(func)(self)
        self.func = func
        self.field = field
        # Cannot use field.name because fields are not yet initialized with __set_name__
        if field is not None and discard is None:
            self.discard: AbstractSet[Field] = {field}
        elif isinstance(discard, Field):
            self.discard = {discard}
        else:
            self.discard = set(discard or ())
        self.dependencies: AbstractSet[str] = set()
        validate = func
        try:
            parameters = signature(func).parameters
        except ValueError:
            self.params: AbstractSet[str] = set()
        else:
            if not parameters:
                raise TypeError("Validator must have at least one parameter")
            if any(p.kind == Parameter.VAR_KEYWORD for p in parameters.values()):
                raise TypeError("Validator cannot have variadic keyword parameter")
            if any(p.kind == Parameter.VAR_POSITIONAL for p in parameters.values()):
                raise TypeError("Validator cannot have variadic positional parameter")
            self.params = set(list(parameters)[1:])
        if isgeneratorfunction(func):
            validate = yield_to_raise(validate)
        if self.field is not None:
            wrapped_field = validate

            def validate(__obj, **kwargs):
                try:
                    wrapped_field(__obj, **kwargs)
                except ValidationError as err:
                    raise ValidationError(children={FieldPath(field): err})

        if self.discard:
            wrapped_discard = validate

            def validate(__obj, **kwargs):
                try:
                    wrapped_discard(__obj, **kwargs)
                except ValidationError as err:
                    raise Discard(self.discard, err)

        self.validate: Callable[..., Iterator[Error]] = validate
        self._registered = False

    def __get__(self, instance, owner):
        return self if instance is None else MethodType(self.func, instance)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def _register(self, owner: Type):
        if self._registered:
            raise RuntimeError("Validator already registered")
        self.dependencies = find_all_dependencies(owner, self.func) | self.params
        _validators[owner].append(self)
        self._registered = True

    def __set_name__(self, owner, name):
        self._register(owner)


T = TypeVar("T")


def validate(__obj: T, __validators: Iterable[Validator] = None, **kwargs) -> T:
    if __validators is None:
        __validators = get_validators(type(__obj))
    error: Optional[ValidationError] = None
    __validators = iter(__validators)
    while True:
        for validator in __validators:
            try:
                if kwargs and validator.params != kwargs.keys():
                    assert all(k in kwargs for k in validator.params)
                    validator.validate(
                        __obj, **{k: kwargs[k] for k in validator.params}
                    )
                else:
                    validator.validate(__obj, **kwargs)
            except ValidationError as err:
                error = merge_errors(error, err)
            except Discard as err:
                error = merge_errors(error, err.error)
                discarded = {f.name for f in err.fields}
                __validators = iter(
                    v for v in __validators if not discarded & v.dependencies
                )
                break
            except NonTrivialDependency as exc:
                exc.validator = validator
                raise
            except AssertionError:
                raise
            except Exception as err:
                error = merge_errors(error, ValidationError([str(err)]))
        else:
            break
    if error is not None:
        raise error
    return __obj


V = TypeVar("V", bound=Callable)


@overload
def validator(func: V) -> V:
    ...


@overload
def validator(
    field: Any = None, *, discard: Any = None, owner: Type = None
) -> Callable[[V], V]:
    ...


def validator(arg=None, *, discard=None, owner=None):
    if arg is None:
        return lambda func: Validator(func, None, discard)
    if callable(arg):
        validator_ = Validator(arg, None, None)
        if is_method(arg) and method_class(arg) is None:
            return validator_
        if is_method(arg):
            if owner is None:
                owner = method_class(arg)
        if owner is None:
            try:
                first_param = next(iter(signature(arg).parameters))
                owner = get_origin_or_type(get_type_hints(arg)[first_param])
            except Exception:
                raise ValueError("Validator first parameter must be typed")
        validator_._register(owner)
        return validator_
    field = arg
    if not isinstance(field, Field):
        raise TypeError(
            "Validator argument must be a field declared with `... = field(...)`"
        )
    if discard is not None:
        if not isinstance(discard, Field) or not (
            isinstance(discard, Collection)
            and all(isinstance(f, Field) for f in discard)
        ):
            raise TypeError("discard must be a field or a collection of fields")
    return lambda func: Validator(func, field, discard)
