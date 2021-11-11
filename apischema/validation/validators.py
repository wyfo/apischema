from collections import defaultdict
from functools import wraps
from inspect import Parameter, isgeneratorfunction, signature
from itertools import chain
from types import MethodType
from typing import (
    AbstractSet,
    Any,
    Callable,
    Collection,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    overload,
)

from apischema.aliases import Aliaser
from apischema.cache import CacheAwareDict
from apischema.methods import is_method, method_class
from apischema.objects import get_alias
from apischema.objects.fields import FieldOrName, check_field_or_name, get_field_name
from apischema.types import AnyType
from apischema.typing import get_type_hints
from apischema.utils import get_origin_or_type2
from apischema.validation.dependencies import find_all_dependencies
from apischema.validation.errors import (
    ValidationError,
    apply_aliaser,
    build_validation_error,
    merge_errors,
)
from apischema.validation.mock import NonTrivialDependency

_validators: MutableMapping[Type, List["Validator"]] = CacheAwareDict(defaultdict(list))


def get_validators(tp: AnyType) -> Sequence["Validator"]:
    return list(
        chain.from_iterable(_validators[cls] for cls in getattr(tp, "__mro__", [tp]))
    )


class Discard(Exception):
    def __init__(self, fields: Optional[AbstractSet[str]], error: ValidationError):
        self.fields = fields
        self.error = error


class Validator:
    def __init__(
        self,
        func: Callable,
        field: FieldOrName = None,
        discard: Collection[FieldOrName] = None,
    ):
        wraps(func)(self)
        self.func = func
        self.field = field
        # Cannot use field.name because fields are not yet initialized with __set_name__
        if field is not None and discard is None:
            self.discard: Optional[Collection[FieldOrName]] = (field,)
        else:
            self.discard = discard
        self.dependencies: AbstractSet[str] = set()
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

            def validate(*args, **kwargs):
                errors = list(func(*args, **kwargs))
                if errors:
                    raise build_validation_error(errors)

            self.validate = validate

        else:
            self.validate = func

    def __get__(self, instance, owner):
        return self if instance is None else MethodType(self.func, instance)

    def __call__(self, *args, **kwargs):
        raise RuntimeError("Method __set_name__ has not been called")

    def _register(self, owner: Type):
        self.owner = owner
        self.dependencies = find_all_dependencies(owner, self.func) | self.params
        _validators[owner].append(self)

    def __set_name__(self, owner, name):
        self._register(owner)
        setattr(owner, name, self.func)


T = TypeVar("T")


def validate(
    obj: T,
    validators: Iterable[Validator] = None,
    kwargs: Optional[Mapping[str, Any]] = None,
    *,
    aliaser: Aliaser = lambda s: s,
) -> T:
    if validators is None:
        validators = get_validators(obj.__class__)
    else:
        validators = list(validators)
    error: Optional[ValidationError] = None
    for i, validator in enumerate(validators):
        try:
            if not kwargs:
                validator.validate(obj)
            elif validator.params == kwargs.keys():
                validator.validate(obj, **kwargs)
            else:
                validator.validate(obj, **{k: kwargs[k] for k in validator.params})
        except ValidationError as e:
            err = apply_aliaser(e, aliaser)
        except NonTrivialDependency as exc:
            exc.validator = validator
            raise
        else:
            continue
        if validator.field is not None:
            alias = getattr(get_alias(validator.owner), get_field_name(validator.field))
            err = ValidationError(children={aliaser(alias): err})
        error = merge_errors(error, err)
        if validator.discard:
            try:
                discarded = set(map(get_field_name, validator.discard))
                next_validators = (
                    v for v in validators[i:] if v.dependencies.isdisjoint(discarded)
                )
                validate(obj, next_validators, kwargs, aliaser=aliaser)
            except ValidationError as err:
                raise merge_errors(error, err)
            else:
                raise error
    if error is not None:
        raise error
    return obj


V = TypeVar("V", bound=Callable)


@overload
def validator(func: V) -> V:
    ...


@overload
def validator(
    field: Any = None, *, discard: Any = None, owner: Type = None
) -> Callable[[V], V]:
    ...


def validator(arg=None, *, field=None, discard=None, owner=None):
    if callable(arg):
        validator_ = Validator(arg, field, discard)
        if is_method(arg):
            cls = method_class(arg)
            if cls is None:
                if owner is not None:
                    raise TypeError("Validator owner cannot be set for class validator")
                return validator_
            elif owner is None:
                owner = cls
        if owner is None:
            try:
                first_param = next(iter(signature(arg).parameters))
                owner = get_origin_or_type2(get_type_hints(arg)[first_param])
            except Exception:
                raise ValueError("Validator first parameter must be typed")
        validator_._register(owner)
        return arg
    else:
        field = field or arg
        if field is not None:
            check_field_or_name(field)
        if discard is not None:
            if not isinstance(discard, Collection) or isinstance(discard, str):
                discard = [discard]
            for discarded in discard:
                check_field_or_name(discarded)
        return lambda func: validator(func, field=field, discard=discard, owner=owner)
