# Validation

Validation is an important part of deserialization. By default, *Apischema* validate types of data according to typing annotations, and [`schema`](json_schema.md#constraints-validation) constraints. But custom validators can also be add for a more precise validation.

## Deserialization and validation error

`ValidationError` is raised when validation fails. This exception will contains all the information about the ill-formed part of the data. By the way this exception is also serializable and can be sent back directly to client.

```python
{!validation_error.py!}
```

As shown in the example, *Apischema* will not stop at the first error met but tries to validate all parts of the data.

## Dataclass validators

Dataclass validation can be completed by custom validators. These are simple decorated methods which will be executed during validation, after all fields having been deserialized.

```python
{!validator.py!}
```

!!! warning
    **DO NOT use `assert`** statement to validate external data, never. In fact, this statement is made to be disabled when executed in optimized mode (see [documentation](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)), so validation would be disabled too. This warning doesn't concern only *Apischema*; `assert` is only for internal assertion in debug/development environment. That's why *Apischema* will not catch `AssertionError` as a validation error but reraises it, making `deserialize` fail. 
    
!!! note
    Validators are alawys executed in order of declaration.

### Automatic dependencies management

It makes no sense to execute a validator using a field that is ill-formed. Hopefully, *Apischema* is able to compute validator dependencies — the fields used in validator; validator is executed only if the all its dependencies are ok.

```python
{!computed_dependencies.py!}
```

!!! note
    Despite the fact that validator use `self` argument, it can be called during validation even if all the fields of the class are not ok and the class not really instantiated. In fact, instance is kind of mocked for validation with only the needed field.

### Raise more than one error with `yield`

Validation of list field can require to raise several exception, one for each bad elements. With `raise`, this is not possible, because you can raise only once.

However, *Apischema* provides a way or raising as many errors as needed by using `yield`. Moreover, with this syntax, it is possible to add a "path" to the error to precise its location in the validated data. This path will be added to the `loc` key of the error.

```python
{!validator_yield.py!}
```

#### Error path

In the example, validator yield a tuple of an "error path" and the error message. Error path can be:

- a string
- an integer (for list indices)
- a dataclass field (obtained with `apischema.fields.fields`)
- a tuple of this 3 components.

`yield` can also be used with only an error message.

!!! note
    For dataclass field error path, it's advised to use `apischema.fields.fields` instead of raw string, because it will take in account potential aliasing and it will be easier to rename field with IDE refactoring.

### Discard

If one of your validators fails because a field is corrupted, maybe you don't want following validators to be executed. `validator` decorator provides a `discard` parameter to discard fields of the remaining validation. All the remaining validators having discarded fields in [dependencies](#automatic-dependencies-management) will not be executed.

```python
{!discard.py!}
```

### Field validators

#### At field level
Fields are validated according to their types and schema. But it's also possible to add validators to fields

```python
{!field_validator.py!}
```

When validation fails for a field, it is discarded and cannot be used in class validators, as it is the case when field schema validation fails.

!!! note
    `field_validator` allow to reuse the the same validator for several fields. However in this case, using a custom type (for example a `NewType`) with validators (see [next section](#validators-for-every-new-types)) could often be a better solution.

#### Using other fields

A common pattern can be to validate a field using other fields values. This is achieved with dataclass validators seen above. However there is a shortcut for this use case:

```python
{!validator_field.py!}
```

### Validators inheritance

Validators are inherited just like other class fields.

```python
{!validator_inheritance.py!}
```

### Validator with `InitVar`

Dataclasses `InitVar` are accessible in validators by using parameters the same way `__post_init__` does. Only the needed fields has to be put in parameters, they are then added to validator dependencies.

```python
{!validator_post_init.py!}
```

### Validators are not run on default values
If all validator dependencies are initialized with their defau
lt values, they are not run; make sure your default values make sens.

```python
{!validator_default.py!}
```

## Validators for every type

Validators can be added to other user-defined types. When a user type is deseriarialized (even in case of [conversion](conversions.md)), its validators are played.

```python
{!validator_user_type.py!}
```

## FAQ

#### How are computed validator depedencies?

`ast.NodeVisitor` and the Python black magic begins...

#### Why only validate at deserialization and not at instantiation?
*Apischema* uses type annotations, so every objects used can already be statically type-checked (with *Mypy*/*Pycharm*/etc.) at instantiation but also at modification.

#### Why use validators for dataclasses instead of doing validation in `__post_init__`?
Actually, validation can completly be done in `__post_init__`, there is not problem with that. However, validators offers one thing that cannot be achieved with `__post_init__`: they are run before `__init__`, so they can validate incomplete data. Moreover, they are only run during deserialization, so they don't add overhead to normal class instantiation.