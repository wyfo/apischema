# JSON schema

## JSON schema generation

JSON schema can be generated from data model. However, because of all possible [customizations](conversions.md), schema can be differ between deserilialization and serialization. In common cases, `deserialization_schema` and `serialization_schema` will give the same result.

```python
{!json_schema.py!}
```

## Field alias

Sometimes dataclass field names can clash with language keyword, sometimes the property name is not convenient. Hopefully, field can define an `alias` which will be used in schema and  deserialization/serialization.

```python
{!alias.py!}
```

!!! warning
    `TypedDict` fields cannot have aliases, see [FAQ]()

### Alias all fields

Field aliasing can also be done at class level by specifying an aliasing function. This aliaser is applied to field alias if defined or field name, or not applied if `override=False` is specified.

```python
{!aliaser.py!}
```

Class-level aliasing can be used to define a *camelCase* API.

### Dynamic aliasing and default aliaser

*apischema* operations `deserialize`/`serialize`/`deserialization_schema`/`serialization_schema` provide an `aliaser` parameter which will be applied on every fields being processed in this operation.

Similar to [`strictness configuration`](de_serialization.md#strictness-configuration), this parameter has a default value controlled by `apischema.settings.aliaser`.

It can be used for example to make all an application use *camelCase*. Actually, there is a shortcut for that:

Otherwise, it's used the same way than [`settings.coercer`](de_serialization.md#strictness-configuration).

```python
from apischema import settings

settings.aliaser(camel_case=True)
```

!!! note
    `NamedTuple` fields are also aliased, but not TypedDict ones; in fact, TypedDict is not a true class, so it is never encountered in serialization, then aliaser cannot be applied to its fields. 

!!! note
    Dynamic aliaser ignores `override=False`
    

## Schema annotations

Type annotations are not enough to express a complete schema, but *apischema* has a function for that; `schema` can be used both as type decorator or field metadata.

```python
{!schema.py!}
```

!!! note
    Schema are particularly useful with `NewType`. For example, if you use prefixed ids, you can use a `NewType` with a `pattern` schema to validate them, and benefit of more precise type checking.
    
The following keys are available (they are sometimes shorten compared to JSON schema original for code concision and snake_case):

Key | JSON schema keyword | type restriction
--- | --- | ---
title | / | /
description | / | /
default | / | /
examples | / | /
min | minimum | `int`
max | maximum | `int`
exc_min | exclusiveMinimum | `int`
exc_max | exclusiveMaximum | `int`
mult_of | multipleOf | `int`
format | / | `str`
min_len | minLength | `str`
max_len | maxLength | `str`
pattern | / | `str`
min_items | minItems | `list`
max_items | maxItems | `list`
unique | / | `list`
min_props | minProperties | `dict`
max_props | maxProperties | `dict`

!!! note
    `schema` function has an overloaded signature which prevents to mix incompatible keywords. 
    
Two other arguments give a finer control of the JSON schema generated: 

- `extra`, either a mapping which will be merged in the schema, or a callable taking the schema dictionary to be modified in place.
- `override=True` prevents *apischema* to use the annotated type schema, using only `schema` annotation, especially `extra` parameter.  

```python
{!schema_extra.py!}
```

### `default` annotation

`default` annotation is not added automatically when a field has a default value (see [FAQ](#why-field-default-value-is-not-used-by-default-to-to-generate-json-schema)); `schema` `default` parameter must be used in order to make it appear in the schema. However `...` can be used as a placeholder to make *apischema* use field default value; this one will be serialized — if serialization fails, error will be ignored as well as `default` annotation.

### Constraints validation

JSON schema constrains the data deserialized; this constraints are naturally used for validation.

```python
{!validation_error.py!}
```

### Default `schema`

When no schema are defined, a default schema can be computed using `settings.default_schema` like this:

```python
from typing import Optional
from apischema import schema, settings
from apischema.json_schema.schemas import Schema


@settings.default_schema
def default_schema(cls) -> Optional[Schema]:
    if not ...:
        return None
    return schema(...)

``` 

Default implementation returns `None` for every types.

## Required field with default value

By default, a dataclass/namedtuple field will be tagged `required` if it doesn't have a default value.

However, you may want to have a default value for a field in order to be more convenient in your code, but still make the field required. One could think about some schema model where version is fixed but is required, for example JSON-RPC with `"jsonrpc": "2.0"`. That's done with field metadata `required`.

```python
{!required.py!}
```

## Additional properties / pattern properties

### With `Mapping`
Schema of a `Mapping`/`dict` type is naturally translated to `"additionalProperties": <schema of the value type>`.

However when the schema of the key has a `pattern`, it will give a `"patternProperties": {<key pattern>: <schema of the value type>}`  

### With dataclass

`additionalProperties`/`patternProperties` can be added to dataclasses by using  fields annotated with `properties` metadata. Properties not mapped on regular fields will be deserialized into this fields; they must have a `Mapping` type (or be [convertible](conversions.md) from `Mapping`) because they are instanciated with a mapping.
 
```python
{!properties.py!}
```
 
!!! note
    Of course, a dataclass can only have a single `properties` field without pattern, because it makes no sens to have several `additionalProperties`.
    
## Property dependencies

*apischema* support [property dependencies](https://json schema.org/understanding-json schema/reference/object.html#property-dependencies) for dataclass through a class member. Dependencies are also used in validation.

!!! note
    JSON schema draft 2019-09 renames properties dependencies `dependentRequired` to disambiguate with schema dependencies

```python
{!dependent_required.py!}
```

Because bidirectional dependencies are a common idiom, *apischema* provides a shortcut notation; it's indeed possible to write `dependent_required([credit_card, billing_adress])`.

## JSON schema reference

For complex schema with type reuse, it's convenient to extract definitions of schema components in order to reuse them; it's even mandatory for recursive types. Then, schema use JSON pointers "$ref" to refer to the definitions. *apischema* handles this feature natively.

```python
{!complex_schema.py!}
```

### Use reference only for reused types

*apischema* can control the reference use through the boolean `all_ref` parameter of `deserialization_schema`/`serialization_schema`: 

- `all_refs=True` -> all types with a reference will be put in the definitions and referenced with `$ref`;
- `all_refs=False` -> only types which are reused in the schema are put in definitions
  
`all_refs` default value depends on the [JSON schema version](#json-schemaopenapi-version): it's `False` for JSON schema drafts but `True` for *OpenAPI*.

```python
{!all_refs.py!}
``` 

### Assign a reference to a type

It's possible to assign a reference name to every type using `apischema.schema_ref`, this name being then used in the schema. It can also be used to remove the reference of a type, by passing `None` instead of a string, so the type can no more be referenced as a separate definition in the schema.


Generic aliases can have a ref, but they need to be specialized; `Foo[T, int]` cannot have a ref but `Foo[str, int]` can.

```python
{!schema_ref.py!}
```

!!! note
    Builtin collections are interchangeable when a ref is registered. For example, if a ref is registered for `list[Foo]`, this ref will also be used for `Sequence[Foo]` or `Collection[Foo]`.

By default, type name will be used for `NewType`s and classes, except unspecialized generic, and primitive ones. This default behavior can be customized using `apischema.settings.default_ref`:

```python
from typing import Optional
from apischema import settings
@settings.default_ref
def default_ref(tp) -> Optional[str]:
    ...
``` 


### Reference factory

`schema_ref` is used to set the reference name, like the name of a class, but in schema, `$ref` looks like `#/$defs/Foo`. In fact, schema generation use the ref given by `schema_ref` and pass it to a `ref_factory` function (a parameter of schema generation functions) which will convert it to its final form. [JSON schema version](#json-schemaopenapi-version) comes with its default `ref_factory`, for draft 2019-09, it prefixes the ref with `#/$defs/`, while it prefixes with `#/components/schema` in case of *OpenAPI*.

```python
{!ref_factory.py!}
```

!!! note
    When `ref_factory` is passed in arguments, definitions are not added to the generated schema. That's because `ref_factory` would surely change definitions location, so there would be no interest to add them with a wrong location. These definitions can of course be generated separately with `definitions_schema`.
    

### Definitions schema

Definitions schemas can also be extracted using `apischema.json_schema.definitions_schema`. It takes two lists `deserialization`/`serialization` of types (or tuple of type + [dynamic conversion](conversions.md)) and returns a dictionary of all referenced schemas.

!!! note
    This is especially useful when it comes to *OpenAPI* schema to generate the components section.

```python
{!definitions_schema.py!}
```

## JSON schema / *OpenAPI* version

JSON schema has several versions — *OpenAPI* is treated as a JSON schema version. If *apischema* natively use the last one: draft 2019-09, it is possible to specify a schema version which will be used for the generation.

```python
{!schema_versions.py!}
```

## `readOnly` / `writeOnly`
Dataclasses `InitVar` and `field(init=False)` fields will be flagged respectively with `"writeOnly": true` and `"readOnly": true` in the generated schema.

In [definitions schema](#definitions-schema), if a type appears both in deserialization and serialization,  properties are merged and the resulting schema contains then `readOnly` and `writeOnly` properties. By the way, the `required` is not merged because it can't (it would mess up validation if some not-init field was required), so deserialization `required` is kept because it's more important as it can be used in validation (*OpenAPI* 3.0 semantic which allows the merge [has been dropped](https://www.openapis.org/blog/2020/06/18/openapi-3-1-0-rc0-its-here) in 3.1, so it has not been judged useful to be supported)

## FAQ

#### Why `TypedDict` doesn't support field aliasing?

`TypedDict` subclasses are not real classes, they are static annotations with no runtime existence, there are only `dict` (or other mappings) at runtime. However, serialization is implemented using runtime classes, as explained [here](conversions.md#why-conversion-can-only-be-applied-on-classes), so `TypedDict` fields are not available during serialization. As a consequence, `TypedDict` field's aliases would not be able to be retrieved by serialization, so they are not supported at all instead of having them at deserialization and not at serialization.  

#### Why field default value is not used by default to generate JSON schema?

Actually, default value is not always the usable in the schema, for example `NotNull` fields with a `None` default value. Because `default` keyword is kind of facultative in the schema, it has been decided to not put it by default in order to not put wrong default by accident.
