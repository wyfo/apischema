# Data model

*apischema* handle every classes/types you need.

By the way, it's done in an additive way, meaning that it doesn't affect your types.

### PEP 585
With Python 3.9 and [PEP 585](https://www.python.org/dev/peps/pep-0585/), typing is substantially shaken up; all container types of `typing` module are now deprecated.

apischema fully support 3.9 and PEP 585, as shown in the different examples. However, `typing` containers can still be used, especially/necessarily when using an older version.  

## Dataclasses

Because the library aims to bring the minimum boilerplate, it's build on the top of standard library. [Dataclasses](https://docs.python.org/3/library/dataclasses.html) are thus the core structure of the data model.

Dataclasses bring the possibility of field customization, with more than just a default value. In addition to the common parameters of [`dataclasses.field`](https://docs.python.org/3/library/dataclasses.html#dataclasses.field), customization is done with `metadata` parameter; metadata can also be passed using PEP 593 `typing.Annotated`.

With some teasing of features presented later:

```python
{!field_metadata.py!}
```

!!! note
    Field's metadata are just an ordinary `dict`; *apischema* provides some functions to enrich these metadata with it's own keys (`alias("foo_bar)` is roughly equivalent to `{"_apischema_alias": "foo_bar"}) and use them when the time comes, but metadata are not reserved to *apischema* and other keys can be added.
   
    Because [PEP 584](https://www.python.org/dev/peps/pep-0584/) is painfully missing before Python 3.9, *apischema* metadata use their own subclass of `dict` just to add `|` operator for convenience in all Python versions.
    
Dataclasses `__post_init__` and `field(init=False)` are fully supported. Implication of this feature usage is documented in the relative sections.

!!! warning
    Before 3.8, `InitVar` is doing [type erasure](https://bugs.python.org/issue33569), that's why it's not possible for *apischema* to retrieve type information of init variables. To fix this behavior, a field metadata `init_var` can be used to put back the type of the field (`init_var` also accepts stringified type annotations).

Dataclass-like types (*attrs*/*SQLAlchemy*/etc.) can also get support with a few lines of code, see [next section](#dataclass-like-types)

## Standard library types

*apischema* handle natively most of the types provided by the standard library. They are sorted in the following categories:

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

- `typing.NamedTuple`

: Handled as an object type, roughly like a dataclass; fields metadata can be passed using `Annotated`

- `typing.TypedDict`

: Hanlded as an object type, but it supports less fields metadata, as explained [here](json_schema.md#why-typeddict-doesnt-support-field-aliasing); in particular, there is no aliasing

- `typing.Any`

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
    To resolve annotations, *apischema* uses `typing.get_type_hints`; this doesn't work really well when used on objects defined outside of global scope.
   
!!! warning "Warning (minor)"
    Currently, PEP 585 can have surprising behavior when used outside the box, see [bpo-41370](https://bugs.python.org/issue41370)
    

## `null` vs `undefined`

Contrary to Javascript, Python doesn't have an `undefined` equivalent (if we consider `None` to be `null` equivalent). But it can be useful to distinguish (especially when thinkinn about HTTP `PATCH` method) between a `null` field and an `undefined`/absent field.

That's why *apischema* provides an `Undefined` constant (a single instance of `UndefinedType` class) which can be used as a default value everywhere where this distinction is needed. In fact, default values are used when field are absent, thus a default `Undefined` will *mark* the field as absent. 

Dataclass/`NamedTuple` fields are ignored by serialization when `Undefined`. 

```python
{!undefined.py!}
```

!!! note
    `UndefinedType` must only be used inside an `Union`, as it has no sense as a standalone type. By the way, no suitable name was found to shorten `Union[T, UndefinedType]` but propositions are welcomed.
    
!!! note
    `Undefined` is a falsy constant, i.e. `bool(Undefined) is False`.
    
## Annotated - PEP 593

[PEP 593](https://www.python.org/dev/peps/pep-0593/) is fully supported; annotations stranger to *apischema* are simply ignored.

### Skip `Union` member

Sometimes, one of the `Union` members has not to be taken in account during validation; it can just be here to match the type of the default value of the field. This member can be marked as to be skipped with [PEP 593](https://www.python.org/dev/peps/pep-0593/) `Annotated` and `apischema.skip.Skip`

```python
{!skip_union.py!}
```

### Optional vs. NotNull

`Optional` type is not always appropriate, because it allows deserialized value to be `null`, but sometimes, you just want `None` as a default value for unset fields, not an authorized one.

That's why *apischema* defines a `NotNull` type; in fact, `NotNull = Union[T, Annotated[None, Skip]]`. 

```python
{!not_null.py!}
```

!!! note
    You can also use [`Undefined`](#null-vs-undefined), but it can be more convenient to directly manipulate an `Optional` field, especially in the rest of the code unrelated to (de)serialization.

## Custom types

*apischema* can support almost all of your types in a few lines of code; see [below](#dataclass-like-types-aka-object-types) for dataclass-like types, and [conversion section](conversions.md) for the rest.

Otherwise, when *apischema* encounters a type that it doesn't support, `Unsupported` exception will be raised.

```python
{!unsupported.py!}
```

### Dataclass-like types, aka object types

Internally, *apischema* handle standard object types — dataclasses, named tuple and typed dictionary — the same way by mapping them to a set of `apischema.objects.ObjectField`, which has the following definition:

```python
@dataclass(frozen=True)
class ObjectField:
    name: str  # field's name
    type: Any  # field's type
    required: bool = True  # if the field is required
    metadata: Mapping[str, Any] = field(default_factory=dict)  # field's metadata 
    default: InitVar[Any] = ...  # field's default value
    default_factory: Optional[Callable[[], Any]] = None  # field's default factory
    aliased: bool = True  # if the fields will be aliased (TypedDict are not)
    kind: FieldKind = FieldKind.NORMAL  # NORMAL/READ_ONLY/WRITE_ONLY
```

Thus, support of dataclass-like types (*attrs*, *SQLAlchemy* traditional mappers, etc.) can be achieved by mapping the concerned class to its own list of `ObjectField`s; this is done using `apischema.objects.set_object_fields`.

```python
{!set_object_fields.py!}
```

## Skip field

Dataclass fields can be excluded from *apischema* processing by using `apischema.metadata.skip` in the field metadata

```python
{!skip_field.py!}   
```
    
    
## Composition over inheritance - composed dataclasses merging

Dataclass fields which are themselves dataclass can be "merged" into the owning one by using `merged` metadata. Then, when the class will be (de)serialized, "merged" fields will be (de)serialized at the same level than the owning class.

```python
{!merged.py!}
```

!!! note
    This feature use JSON schema draft 2019-09 [`unevaluatedProperties` keyword](https://json-schema.org/draft/2019-09/json-schema-core.html#unevaluatedProperties). However, this keyword is removed when JSON schema is converted in a version that doesn't support it, like OpenAPI 3.0.

This feature is very convenient for building model by composing smaller components. If some kind of reuse could also be achieved with inheritance, it can be less practical when it comes to use it in code, because there is no easy way to build an inherited class when you have an instance of the super class ; you have to copy all the fields by hand. On the other hand, using composition (of merged fields), it's easy to instantiate the class when the smaller component is just a field of it.

## FAQ

#### Why `Iterable` is not handled with other collection type?
Iterable could be handled (actually, it was at the beginning), however, this doesn't really make sense from a data point of view. Iterable are computation objects, they can be infinite, etc. They don't correspond to a serialized data; `Collection` is way more appropriate in this context.

#### What happens if I override dataclass `__init__`?
*apischema* always assumes that dataclass `__init__` can be called with with all its fields as kwargs parameters. If that's no more the case after a modification of `__init__` (what means if an exception is thrown when the constructor is called because of bad parameters), *apischema* treats then the class as [not supported](#unsupported-types).
