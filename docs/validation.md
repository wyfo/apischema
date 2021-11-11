# Validation

Validation is an important part of deserialization. By default, *apischema* validates types of data according to typing annotations, and [`schema`](json_schema.md#constraints-validation) constraints. But custom validators can also be add for a more precise validation.

## Deserialization and validation error

`ValidationError` is raised when validation fails. This exception contains all the information about the ill-formed part of the data. It can be formatted/serialized using its `errors` property. 

```python
{!validation_error.py!}
```

As shown in the example, *apischema* will not stop at the first error met but tries to validate all parts of the data.

!!! note
    `ValidationError` can also be serialized using `apischema.serialize` (this will use `errors` internally).

## Constraint errors customization

Constraints are validated at deserialization, with *apischema* providing default error messages.
Messages can be customized by setting the corresponding attribute of `apischema.settings.errors`. They can be either a string which will be formatted with the constraint value (using `str.format`), e.g. `less than {} (minimum)`, or a function with 2 parameters: the constraint value and the invalid data. 

```python
{!settings_errors.py!}
```

!!! note
    Default error messages doesn't include the invalid data for security reason (data could for example be a password too short).

!!! note
    Other error message can be customized, for example `missing property` for missing required properties, etc.

## Dataclass validators

Dataclass validation can be completed by custom validators. These are simple decorated methods which will be executed during validation, after all fields having been deserialized.

!!! note
    Previously to v0.17, validators could raise arbitrary exceptions (except AssertionError of course); see [FAQ](#why-validators-cannot-raise-arbitrary-exception) for the reason of this change.

```python
{!validator.py!}
```

!!! warning
    **DO NOT use `assert`** statement to validate external data, ever. In fact, this statement is made to be disabled when executed in optimized mode (see [documentation](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)), so validation would be disabled too. This warning doesn't concern only *apischema*; `assert` is only for internal assertion in debug/development environment. That's why *apischema* will not catch `AssertionError` as a validation error but reraises it, making `deserialize` fail. 
    
!!! note
    Validators are always executed in order of declaration.

### Automatic dependency management

It makes no sense to execute a validator using a field that is ill-formed. Hopefully, *apischema* is able to compute validator dependencies — the fields used in validator; validator is executed only if the all its dependencies are ok.

```python
{!computed_dependencies.py!}
```

!!! note
    Despite the fact that validator uses the `self` argument, it can be called during validation even if all the fields of the class are not ok and the class not really instantiated. In fact, instance is kind of mocked for validation with only the needed field.

### Raise more than one error with `yield`

Validation of a list field can require raising several exceptions, one for each bad element. With `raise`, this is not possible, because you can raise only once.

However, *apischema* provides a way of raising as many errors as needed by using `yield`. Moreover, with this syntax, it is possible to add a "path" (see [below](#error-path)) to the error to precise its location in the validated data. This path will be added to the `loc` key of the error.

```python
{!validator_yield.py!}
```

#### Error path

In the example, the validator yields a tuple of an "error path" and the error message. Error path can be:

- a field alias (obtained with `apischema.objects.get_alias`);
- an integer, for list indices;
- a raw string, for dict key (or field);
- an `apischema.objects.AliasedStr`, a string subclass which will be aliased by deserialization aliaser;
- an iterable, e.g. a tuple, of this 4 components.

`yield` can also be used with only an error message.

!!! note
    For dataclass field error path, it's advised to use `apischema.objects.get_alias` instead of raw string, because it will take into account potential aliasing and it will be better handled by IDE (refactoring, cross-referencing, etc.)

### Discard

If one of your validators fails because a field is corrupted, maybe you don't want subsequent validators to be executed. `validator` decorator provides a `discard` parameter to discard fields of the remaining validation. All the remaining validators having discarded fields in [dependencies](#automatic-dependencies-management) will not be executed.

```python
{!discard.py!}
```

You can notice in this example that *apischema* tries to avoid using raw strings to identify fields. In every function of the library using fields identifier (`apischema.validator`, `apischema.dependent_required`, `apischema.fields.set_fields`, etc.), you have always three ways to pass them:
- using field object, preferred in dataclass definition;
- using `apischema.objects.get_field`, to be used outside of class definition; it works with `NamedTuple` too — the object returned is the *apischema* internal field representation, common to `dataclass`, `NamedTuple` and `TypedDict`;
- using raw strings, thus not handled by static tools like refactoring, but it works;

### Field validators

#### At field level
Fields are validated according to their types and schema. But it's also possible to add validators to fields.

```python
{!field_validator.py!}
```

When validation fails for a field, it is discarded and cannot be used in class validators, as is the case when field schema validation fails.

!!! note
    `field_validator` allows reusing the the same validator for several fields. However in this case, using a custom type (for example a `NewType`) with validators (see [next section](#validators-for-every-new-types)) could often be a better solution.

#### Using other fields

A common pattern can be to validate a field using other fields values. This is achieved with dataclass validators seen above. However, there is a shortcut for this use case:

```python
{!validator_field.py!}
```

### Validators inheritance

Validators are inherited just like other class fields.

```python
{!validator_inheritance.py!}
```

### Validator with `InitVar`

Dataclasses `InitVar` are accessible in validators by using parameters the same way `__post_init__` does. Only the needed fields have to be put in parameters, they are then added to validator dependencies.

```python
{!validator_post_init.py!}
```

### Validators are not run on default values
If all validator dependencies are initialized with their default values, they are not run.

```python
{!validator_default.py!}
```

## Validators for every type

Validators can also be declared as regular functions, in which case annotation of the first param is used to associate it to the validated type (you can also use the `owner` parameter); this allows adding a validator to every type.

Last but not least, validators can be embedded directly into `Annotated` arguments using `validators` metadata.

```python
{!validator_function.py!}
```

## FAQ

#### How are validator dependencies computed?

`ast.NodeVisitor` and the Python black magic begins...

#### Why only validate at deserialization and not at instantiation?
*apischema* uses type annotations, so every objects used can already be statically type-checked (with *Mypy*/*Pycharm*/etc.) at instantiation but also at modification.

#### Why use validators for dataclasses instead of doing validation in `__post_init__`?
Actually, validation can completely be done in `__post_init__`, there is no problem with that. However, validators offers one thing that cannot be achieved with `__post_init__`: they are run before `__init__`, so they can validate incomplete data. Moreover, they are only run during deserialization, so they don't add overhead to normal class instantiation.

#### Why validators cannot raise arbitrary exception?

Allowing arbitrary exception is in fact a security issue, because unwanted exception could be raised, and their message displayed in validation error. It could either contain sensitive data, or give information about the implementation which could be used to hack it.

By the way, it's possible to define a decorator to convert precise exceptions to `ValidationError`:
```python
from collections.abc import Callable
from functools import wraps
from typing import TypeVar
from apischema import ValidationError

Func = TypeVar("Func", bound=Callable)
def catch(*exceptions) -> Callable[[Func], Func]:
    def decorator(func: Func) -> Func:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as err:
                raise ValidationError(str(err)) if isinstance(err, exceptions) else err
        return wrapper
    return decorator
```