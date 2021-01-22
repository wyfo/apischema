# (De)serialization

*Apischema* aims to help API with deserialization/serialization of data, mostly JSON.

Let start again with the [overview example](index.md#example)
```python
{!quickstart.py!}
```

## Deserialization

Deserialization is done through the function `apischema.deserialize` with the following simplified signature:
```python
def deserialize(cls: Type[T], data: Any) -> T:
    ...
```
- `cls` can be a `dataclass` as well as a `list[int]` a `NewType`, or whatever you want (see [conversions](conversions.md) to extend deserialization support to every type you want).
- `data` must be a JSON-like serialized data: `dict`/`list`/`str`/`int`/`float`/`bool`/`None`, in short, what you get when you execute `json.loads`.

Deserialization performs a validation of data, based on typing annotations and other information (see [schema](json_schema.md) and [validation](validation.md)).

{!deserialization.py!}

### Strictness

#### Coercion

*Apischema* is strict by default. You ask for an integer, you have to receive an integer. 

However, in some cases, data has to be be coerced, for example when parsing aconfiguration file. That can be done using `coerce` parameter; when set to `True`, all primitive types will be coerce to the expected type of the data model like the following:

```python
{!coercion.py!}
```

`bool` can be coerced from `str` with the following case-insensitive mapping:

| False | True |
| --- | --- |
| 0 | 1 |
| f | t |
| n | y |
| no | yes |
| false | true |
| off | on |
| ko | ok |

!!! note
    `bool` coercion from `str` is just a global `dict[str, bool]` named `apischema.data.coercion.STR_TO_BOOL` and it can be customized according to your need (but keys have to be lower cased).
    
    There is also a global `set[str]` named `apischema.data.coercion.STR_NONE_VALUES` for `None` coercion.
    
`coercion` parameter can also receive a coercion function which will then be used instead of default one.

```python
{!coercion_function.py!}
```

!!! note
    If coercer result is not an instance of class passed in argument, a ValidationError will be raised with an appropriate error message
    
!!! warning
    Coercer first argument is a primitive json type `str`/`bool`/`int`/`float`/`list`/`dict`/`type(None)`; it can be `type(None)`, so returning `cls(data)` will fail in this case.
    
#### Additional properties

*Apischema* is strict too about number of fields received for an *object*. In JSON schema terms, *Apischema* put `"additionalProperties": false` by default (this can be configured by class with [properties field](#additional-and-pattern-properties)). 

This behavior can be controlled by `additional_properties` parameter. When set to `True`, it prevents the reject of unexpected properties. 

```python
{!additional_properties.py!}
```

#### Default fallback

Validation error can happen when deserializing an ill-formed field. However, if this field has a default value/factory, deserialization can fallback to this default; this is enabled by `default_fallback` parameter. This behavior can also be configured for each field using metadata. 

```python
{!default_fallback.py!}
```

#### Strictness configuration

*Apischema* global configuration is managed through `apischema.settings` module.
This module has, among other, three global variables `settings.additional_properties`, `settings.coercion` and `settings.default_fallback` whose values are used as default parameter values for the `deserialize` function.

Global coercion function can be set with `settings.coercer` following this example:

```python
import json
from apischema import ValidationError, settings

prev_coercer = settings.coercer()

@settings.coercer
def coercer(cls, data):
    """In case of coercion failures, try to deserialize json data"""
    try:
        return prev_coercer(cls, data)
    except ValidationError as err:
        if not isinstance(data, str):
            raise
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            raise err
```

!!! note
    Like all `settings` function, `coercer` has an overloaded signature. Without argument, it returns the current settings function, and with an argument, it set the settings function.

## Fields set

Sometimes, it can be useful to know which field has been set by the deserialization, for example in the case of a *PATCH* requests, to know which field has been updated. Moreover, it is also used in serialization to limit the fields serialized (see [next section](#exclude-unset-fields))

Because *Apischema* use vanilla dataclasses, this feature is not enabled by default and must be set explicitly on a per-class basis. *Apischema* provides a simple API to get/set this metadata.  

```python
{!fields_set.py!}
```

!!! warning
    `with_fields_set` decorator MUST be put above `dataclass` one. This is because both of them modify `__init__` method, but only the first is built to take the second in account.
    
!!! warning
    `dataclasses.replace` works by setting all the fields of the replaced object. Because of this issue, *Apischema* provides a little wrapper `apischema.dataclasses.replace`.


## Serialization

Serialization is simpler than deserialization; `serialize(obj)` will generate a JSON-like serialized `obj`.

There is no validation, objects provided are trusted — they are supposed to be statically type-checked. When there

```python
{!serialization.py!}
```

    
### Serialized methods/properties

*Apischema* can execute methods/properties during serialization and add the computed values with the other fields values; just put `apischema.serialized` decorator on top of methods/properties you want to be serialized.

The function name is used unless an alias is given in decorator argument.

```python
{!serialized.py!}
```

!!! note
    Serialized methods must not have parameters without default, as *Apischema* need to execute them without arguments

!!! note
    Overriding of a serialized method in a subclass will also override the serialization of the subclass. 

#### Error handling

Errors occurring in serialized methods can be caught in a dedicated error handler registered with `error_handler` parameter. This function takes in parameters the exception, the object and the alias of the serialized method; it can return a new value or raise the current or another exception — it can for example be used to log errors without throwing the complete serialization.

The resulting serialization type will be a `Union` of the normal type and the error handling type ; if the error handler always raises, use [`typing.NoReturn`](https://docs.python.org/3/library/typing.html#typing.NoReturn) annotation. 

`error_handler=None` correspond to a default handler which only return `None` — exception is thus discarded and serialization type becomes `Optional`.

The error handler is only executed by *Apischema* serialization process, it's not added to the function, so this one can be executed normally and raise an exception in the rest of your code.

```python
{!serialized_error.py!}
```

#### Non-required serialized methods

Serialized methods (or their error handler) can return `apischema.Undefined`, in which case the property will not be included into the serialization; accordingly, the property loose the *required* qualification in the JSON schema.

```python
{!serialized_undefined.py!}
```

#### Generic serialized methods

Serialized methods of generic classes get the right type when their owning class is specialized.

```python
{!serialized_generic.py!}
```
!!! warning
`serialized` cannot decorate methods of `Generic` classes in Python 3.6, it has to be used outside of class.

### Exclude unset fields

When a class has a lot of optional fields, it can be convenient to not include all of them, to avoid a bunch of useless fields in your serialized data.
Using the previous feature of [fields set tracking](#fields-set), `serialize` can exclude unset fields using its `exclude_unset` parameter or `settings.exclude_unset` (default is `True`).

```python
{!exclude_unset.py!}
```

!!! note
    As written in comment in the example, `with_fields_set` is necessary to benefit from the feature. If the dataclass don't use it, the feature will have no effect.
    
Sometimes, some fields must be serialized, even with their default value; this behavior can be enforced using field metadata. With it, field will be marked as set even if its default value is used at initialization.

```python
{!default_as_set.py!}
```

!!! note
    This metadata has effect only in combination with `with_fields_set` decorator.
    
## FAQ

#### Why coercion is not default behavior?
Because ill-formed data can be symptomatic of problems, and it has been decided that highlighting them would be better than hiding them. By the way, this is easily globally configurable.

#### Why `with_fields_set` feature is not enable by default?
It's true that this feature has the little cost of adding a decorator everywhere. However, keeping dataclass decorator allows IDEs/linters/type checkers/etc. to handle the class as such, so there is no need to develop a plugin for them. Standard compliance can be worth the additional decorator. (And little overhead can be avoided when not useful)