# Data model

*Apischema* handle every classes/types you need.

By the way, it's done in an additive way, meaning that it doesn't affect your types.

### PEP 585
With Python 3.9 and [PEP 585](https://www.python.org/dev/peps/pep-0585/), typing is substantially shaken up; all collection types of `typing` module are now deprecated.

Apischema fully support 3.9 and PEP 585, as shown in the different examples.

## Dataclasses

Because the library aims to bring the minimum boilerplate, it's build on the top of standard library. [Dataclasses](https://docs.python.org/3/library/dataclasses.html) are thus the core structure of the data model.

Dataclasses bring the possibility of field customization, with more than just a default value.
In addition to the common parameters of [`dataclasses.field`](https://docs.python.org/3/library/dataclasses.html#dataclasses.field), customization is done with `metadata` parameter. 

With some teasing of features presented later:
```python
{!field_metadata.py!}
```


!!! note
    Field's metadata are just an ordinary `dict`; *Apischema* provides some functions to enrich these metadata with it's own keys (`alias("foo_bar)` is roughly equivalent to `{"_apischema_alias": "foo_bar"}) and use them when the time comes, but metadata are not reserved to *Apischema* and other keys can be added.
   
    Because [PEP 584](https://www.python.org/dev/peps/pep-0584/) is painfully missing before Python 3.9, *Apischema* metadata use their own subclass of `dict` just to add `|` operator for convenience.
    
Dataclasses `__post_init__` and `field(init=False)` are fully supported. Implication of this feature usage is documented in the relative sections.

!!! warning
    Before 3.8, `InitVar` is doing [type erasure](https://bugs.python.org/issue33569), that's why it's not possible for *Apischema* to retrieve type information of init variables. To fix this behavior, a field metadata `init_var` can be used to put back the type of the field (`init_var` also accepts stringified type annotations).

## Standard library types

*Apischema* handle natively most of the types provided by the standard library. They are sorted in the following categories:

#### Primitive
`str`, `int`, `float`, `bool`, `None`, subclasses of them

They correspond to JSON primitive types.

#### Collection

- `collection.abc.Collection` (*`typing.Collection`*)
- `collection.abc.Sequence` (*`typing.Sequence`*)
- `tuple` (*`typing.Tuple`*)
- `collection.abc.MutableSequence` (*`typing.MutableSequence`*)
- `list` (*`typing.List`*)
- `collection.abc.Set` (*`typing.AbstractSet`*)
- `collection.abc.MutableSet` (*`typing.MutableSet`*)
- `frozenset` (*`typing.FrozenSet`*)
- `set` (*`typing.Set`*)

They correspond to JSON *array* and are serialized to `list`.

Some of them are abstract; deserialization will instantiate a concrete child class. For example `collection.abc.Sequence` will be instantiated with `tuple` while `collection.MutableSequence` will be instantiated with `list`.


#### Mapping

- `collection.abc.Mapping` (*`typing.Mapping`*)
- `collection.abc.MutableMapping` (*`typing.MutableMapping`*)
- `dict` (*`typing.Dict`*)

They correpond to JSON *object* and are serialized to `dict`.

#### Enumeration

`enum.Enum` subclasses, `typing.Literal`

For `Enum`, this is the value and not the attribute name that is serialized

#### Typing facilities

- `typing.Optional`/`typing.Union` (`Optional[T]` is strictly equivalent to `Union[T, None]`)

: Deserialization select the first matching alternative (see below how to [skip some union member](#skip-union-member))

- `tuple` (*`typing.Tuple`*)

: Can be used as collection as well as true tuple, like `tuple[str, int]`

- `typing.NewType`

: Serialized according to its base type

- `typing.TypedDict`, `typing.NamedTuple`

: Kind of discount dataclass without field customization

- `Any`

: Untouched by deserialization

#### Other standard library types

- `bytes`

: with `str` (de)serialization using base64 encoding

- `datetime.datetime`
- `datetime.date`
- `datetime.time`

: Supported only in 3.7+ with `fromisoformat`/`isoformat`

- `Decimal`

: With `float` (de)serialization

- `ipaddress.IPv4Address` 
- `ipaddress.IPv4Interface`
- `ipaddress.IPv4Network`
- `ipaddress.IPv6Address` 
- `ipaddress.IPv6Interface`
- `ipaddress.IPv6Network`
- `pathlib.Path`
- `re.Pattern` (*`typing.Pattern`*)
- `uuid.UUID`

: With `str` (de)serialization

## Generic

`typing.Generic` can be used out of the box like in the following example:
```python
{!generic.py!}
```

## Recursive types, string annotations and PEP 563

Recursive classes can be typed as they usually do, with or without [PEP 563](https://www.python.org/dev/peps/pep-0563/).
Here with string annotations:
```python
{!recursive.py!}
```
Here with PEP 563 (requires 3.7+)
```python
{!recursive_postponned.py!}
```
!!! warning
    To resolve annotations, *Apischema* uses `typing.get_type_hints`; this doesn't work really well when used on objects defined outside of global scope.
   
!!! warning "Warning (minor)"
    Currently, PEP 585 can have surprising behavior when used outside the box, see [bpo-41370](https://bugs.python.org/issue41370)


## Annotated - PEP 593

[PEP 593](https://www.python.org/dev/peps/pep-0593/) is fully supported; annotations stranger to *Apischema* are simlply ignored.

## Skip `Union` member

Sometimes, one of the `Union` members has not to be taken in account during validation; it can just be here to match the type of the default value of the field. This member can be marked as to be skipped with [PEP 593](https://www.python.org/dev/peps/pep-0593/) `Annotated`

```python
{!skip_union.py!}
```

!!! note
    `Skip(schema_only=True)` can also be used to skip the member only for [JSON schema generation](json_schema.md)

### Optional vs. NotNull

`Optional` type is not always appropriate, because it allows deserialized value to be `null`, but sometimes, you just want `None` as a default value for unset fields, not an authorized one.

To solve this issue, *Apischema* defines a `NotNull` type. 

```python
{!not_null.py!}
```

!!! note
    In fact, `NotNull = Union[T, Annotated[None, Skip]]`. 
    
    
## Composed dataclasses merging

Dataclass fields which are themselves dataclass can be "merged" into the owning one by using `merged` metadata.

```python
{!merged.py!}
```

!!! note
    This feature use JSON schema draft 2019-09 [`unevaluatedProperties` keyword](https://json-schema.org/draft/2019-09/json-schema-core.html#unevaluatedProperties).
    

## Custom types / ORM

See [conversion](conversions.md) in order to support every possible types in a few lines of code.

## Unsupported types

When *Apischema* encounters a type that it doesn't support, `Unsupported` exception will be raised.

```python
{!unsupported.py!}
```

See [conversion](conversions.md) section to make *Apischema* support all your classes.

## FAQ

#### Why `Iterable` is not handled with other collection type?
Iterable could be handled (actually, it was at the beginning), however, this doesn't really make sense from a data point of view. Iterable are computation objects, they can be infinite, etc. They don't correspond to a serialized data; `Collection` is way more appropriate in this context.

#### What happens if I override dataclass `__init__`?
*Apischema* always assumes that dataclass `__init__` can be called with with all its fields as kwargs parameters. If that's no more the case after a modification of `__init__` (what means if an exception is thrown when the constructor is called because of bad parameters), *Apischema* treats then the class as [not supported](#unsupported-types).
