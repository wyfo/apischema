# Data model

*apischema* handles every class/type you need.

By the way, it's done in an additive way, meaning that it doesn't affect your types.

### PEP 585
With Python 3.9 and [PEP 585](https://www.python.org/dev/peps/pep-0585/), typing is substantially shaken up; all container types of `typing` module are now deprecated.

apischema fully support 3.9 and PEP 585, as shown in the different examples. However, `typing` containers can still be used, especially/necessarily when using an older version.  

## Dataclasses

Because the library aims to bring the minimum boilerplate, it's built on the top of standard library. [Dataclasses](https://docs.python.org/3/library/dataclasses.html) are thus the core structure of the data model.

Dataclasses bring the possibility of field customization, with more than just a default value. In addition to the common parameters of [`dataclasses.field`](https://docs.python.org/3/library/dataclasses.html#dataclasses.field), customization is done with the `metadata` parameter; metadata can also be passed using PEP 593 `typing.Annotated`.

With some teasing of features presented later:

```python
{!field_metadata.py!}
```

!!! note
    Field's metadata are just an ordinary `dict`; *apischema* provides some functions to enrich these metadata with its own keys (`alias("foo_bar)` is roughly equivalent to `{"_apischema_alias": "foo_bar"}) and use them when the time comes, but metadata are not reserved to *apischema* and other keys can be added.
   
    Because [PEP 584](https://www.python.org/dev/peps/pep-0584/) is painfully missing before Python 3.9, *apischema* metadata use their own subclass of `dict` just to add `|` operator for convenience in all Python versions.
    
Dataclasses `__post_init__` and `field(init=False)` are fully supported. Implications of this feature usage are documented in the relative sections.

!!! warning
    Before 3.8, `InitVar` is doing [type erasure](https://bugs.python.org/issue33569), which is why it's not possible for *apischema* to retrieve type information of init variables. To fix this behavior, a field metadata `init_var` can be used to put back the type of the field (`init_var` also accepts stringified type annotations).

Dataclass-like types (*attrs*/*SQLAlchemy*/etc.) can also be supported with a few lines of code, see [next section](#dataclass-like-types)

## Standard library types

*apischema* natively handles most of the types provided by the standard library. They are sorted in the following categories:

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

#### Mapping

- `collection.abc.Mapping` (*`typing.Mapping`*)
- `collection.abc.MutableMapping` (*`typing.MutableMapping`*)
- `dict` (*`typing.Dict`*)

They correpond to JSON *object* and are serialized to `dict`.

#### Enumeration

`enum.Enum` subclasses, `typing.Literal`

!!! warning
    `Enum` subclasses are (de)serialized using **values**, not names. *apischema* also provides a [conversion](conversions.md#using-enum-names) to use names instead.

#### Typing facilities

- `typing.Optional`/`typing.Union` (`Optional[T]` is strictly equivalent to `Union[T, None]`)

: Deserialization select the first matching alternative; unsupported alternatives are ignored

- `tuple` (*`typing.Tuple`*)

: Can be used as collection as well as true tuple, like `tuple[str, int]`

- `typing.NewType`

: Serialized according to its base type

- `typing.NamedTuple`

: Handled as an object type, roughly like a dataclass; fields metadata can be passed using `Annotated`

- `typing.TypedDict`

: Hanlded as an object type, but with a dictionary shape; fields metadata can be passed using `Annotated`

- `typing.Any`

: Untouched by deserialization, serialized according to the object runtime class

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

!!! warning
    Generic types don't have default *type name* (used in JSON/GraphQL schema) — should `Group[Foo]` be named `GroupFoo`/`FooGroup`/something else? — so they require by-class or default [`type_name` assignment](json_schema.md#set-reference-name).

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
    

## `null` vs. `undefined`

Contrary to Javascript, Python doesn't have an `undefined` equivalent (if we consider `None` to be the equivalent of `null`). But it can be useful to distinguish (especially when thinking about HTTP `PATCH` method) between a `null` field and an `undefined`/absent field.

That's why *apischema* provides an `Undefined` constant (a single instance of `UndefinedType` class) which can be used as a default value everywhere where this distinction is needed. In fact, default values are used when field are absent, thus a default `Undefined` will *mark* the field as absent. 

Dataclass/`NamedTuple` fields are ignored by serialization when `Undefined`. 

```python
{!undefined.py!}
```

!!! note
    `UndefinedType` must only be used inside an `Union`, as it has no sense as a standalone type. By the way, no suitable name was found to shorten `Union[T, UndefinedType]` but propositions are welcomed.
    
!!! note
    `Undefined` is a falsy constant, i.e. `bool(Undefined) is False`.

### Use `None` as if it was `Undefined`

Using `None` can be more convenient than `Undefined` as a placeholder for missing value, but `Optional` types are translated to nullable fields.

That's why *apischema* provides `none_as_undefined` metadata, allowing `None` to be handled as if it was `Undefined`: type will not be nullable and field not serialized if its value is `None`.

```python
{!none_as_undefined.py!}
```
    
## Annotated - PEP 593

[PEP 593](https://www.python.org/dev/peps/pep-0593/) is fully supported; annotations stranger to *apischema* are simply ignored.

## Custom types

*apischema* can support almost all of your custom types in a few lines of code, using the [conversion feature](conversions.md). However, it also provides a simple and direct way to support dataclass-like types, as presented [below](#dataclass-like-types-aka-object-types).

Otherwise, when *apischema* encounters a type that it doesn't support, `apischema.Unsupported` exception will be raised.

!!! note
    In the rare case when a union member should be ignored by apischema, it's possible to use mark it as unsupported using `Union[Foo, Annotated[Bar, Unsupported]]`.

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
    kind: FieldKind = FieldKind.NORMAL  # NORMAL/READ_ONLY/WRITE_ONLY
```

Thus, support of dataclass-like types (*attrs*, *SQLAlchemy* traditional mappers, etc.) can be achieved by mapping the concerned class to its own list of `ObjectField`s; this is done using `apischema.objects.set_object_fields`.

```python
{!set_object_fields.py!}
```

Another way to set object fields is to directly modify *apischema* default behavior, using `apischema.settings.default_object_fields`.

!!! note
    `set_object_fields`/`settings.default_object_fields` can be used to override existing fields. Current fields can be retrieved using `apischema.objects.object_fields`.

```python
from collections.abc import Sequence
from typing import Optional
from apischema import settings
from apischema.objects import ObjectField

previous_default_object_fields = settings.default_object_field


def default_object_fields(cls) -> Optional[Sequence[ObjectField]]:
    return [...] if ... else previous_default_object_fields(cls)


settings.default_object_fields = default_object_fields
``` 

!!! note
    Almost every default behavior of apischema can be customized using `apischema.settings`.

Examples of [*SQLAlchemy* support](examples/sqlalchemy_support.md) and [attrs support](examples/attrs_support.md) illustrate both methods (which could also be combined).

## Skip field

Dataclass fields can be excluded from *apischema* processing by using `apischema.metadata.skip` in the field metadata. It can be parametrized with `deserialization`/`serialization` boolean parameters to skip a field only for the given operations.

```python
{!skip.py!}   
```

!!! note
    Fields skipped in deserialization should have a default value if deserialized, because deserialization of the class could raise otherwise.

### Skip field serialization depending on condition

Field can also be skipped when serializing, depending on the condition given by `serialization_if`, or when the field value is equal to its default value with `serialization_default=True`.

```python
{!skip_if.py!}   
```
    
## Composition over inheritance - composed dataclasses flattening

Dataclass fields which are themselves dataclass can be "flattened" into the owning one by using `flatten` metadata. Then, when the class is (de)serialized, "flattened" fields will be (de)serialized at the same level as the owning class.

```python
{!flattened.py!}
```

!!! note
    Generated JSON schema use [`unevaluatedProperties` keyword](https://json-schema.org/understanding-json-schema/reference/object.html?highlight=unevaluated#unevaluated-properties).

This feature is very convenient for building model by composing smaller components. If some kind of reuse could also be achieved with inheritance, it can be less practical when it comes to use it in code, because there is no easy way to build an inherited class when you have an instance of the super class; you have to copy all the fields by hand. On the other hand, using composition (of flattened fields), it's easy to instantiate the class when the smaller component is just a field of it.

## FAQ

#### Why isn't `Iterable` handled with other collection types?
Iterable could be handled (actually, it was at the beginning), however, this doesn't really make sense from a data point of view. Iterables are computation objects, they can be infinite, etc. They don't correspond to a serialized data; `Collection` is way more appropriate in this context.

#### What happens if I override dataclass `__init__`?
*apischema* always assumes that dataclass `__init__` can be called with all its fields as kwargs parameters. If that's no longer the case after a modification of `__init__` (what means if an exception is thrown when the constructor is called because of bad parameters), *apischema* treats then the class as [not supported](#unsupported-types).
