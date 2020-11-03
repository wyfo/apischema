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

### Alias all fields

Field aliasing can also be done at class level by specifying an aliasing function. This aliaser is applied to field alias if defined or field name, or not applied if `override=False` is specified.

```python
{!aliaser.py!}
```

Class-level aliasing can be used to define a *camelCase* API.

### Global aliaser

`apischema.settings.aliaser` can be used to set a global aliaser function which will be applied to every field (`override=False` is ignored by the global aliaser).

It can be used for example to make all an application use *camelCase*. Actually, there is a shortcut for that:

```python
from apischema import settings

settings.aliaser(camel_case=True)
```

Otherwise, it's used the same way than [`settings.coercer`](de_serialization.md#strictness-configuration).

## Schema annotations

Type annotations are not enough to express a complete schema, but *Apischema* has a function for that; `schema` can be used both as type decorator or field metadata.

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
    
Two other arguments enable a finer control of the JSON schema generated : 

- `extra` enable to add arbitrary keys to schema;
- `override=True` prevents *Apischema* to use the annotated type schema, using only `schema` annotation.  

```python
{!schema_extra.py!}
```

### `default` annotation

`default` annotation is not added automatically when a field has a default value (see [FAQ](#why-field-default-value-is-not-used-by-default-to-to-generate-json-schema)); `schema` `default` parameter must be used in order to make it appear in the schema. However `...` can be used as a placeholder to make *Apischema* use field default value; this one will be serialized — if serialization fails, error will be ignored as well as `default` annotation.

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
from apischema.json_schema.schema import Schema
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

*Apischema* support [property dependencies](https://json schema.org/understanding-json schema/reference/object.html#property-dependencies) for dataclass through a class member. Dependencies are also used in validation.

!!! note
    JSON schema draft 2019-09 renames properties dependencies `dependentRequired` to disambiguate with schema dependencies

```python
{!dependent_required.py!}
```

Because bidirectional dependencies are a common idiom, *Apischema* provides a shortcut notation. Its indeed possible to write `DependentRequired([credit_card, billing_adress])`.

## Complex/recursive types - JSON schema definitions/OpenAPI components

For complex schema with type reuse, it's convenient to extract definitions of schema components in order to reuse them; it's even mandatory for recursive types. Then, schema use JSON pointers "$ref" to refer to the definitions. *Apischema* handles this feature natively.

```python
{!complex_schema.py!}
```

### Use ref only for reused types

If some types appear only once in the schema, you maybe don't want to use a `$ref` and a definition but inline the type definition directly. It is possible by setting `schema_ref(None)` (see [next section](#customize-ref)) on the the concerned type, but it could affect others schema where this types is reused several time. 

However, *Apischema* provides a parameter `all_ref` for this reason:
- `all_refs=True` -> all types with a reference will be put in the definitions and referenced with `$ref`;
- `all_refs=False` -> only types which are reused in the schema are put in definitions
`all_refs` default value depends on the [JSON schema version](#json-schemaopenapi-version): it's `False` for JSON schema drafts but `True` for *OpenAPI*.

```python
{!all_refs.py!}
``` 


### Definitions schema only

Sometimes you need to extract only the definitions in a separate schema (especially OpenAPI components). That's done with the `definitions_schema` function. It takes two lists `deserializations` and `serializations` of schema (or schema + [conversions](conversions.md)) and combines the definitions of all the schema that would have been generated with types given in the list of schema.

```python
{!definitions_schema.py!}
```

## Customize `$ref`

### Add `$ref` to every types

In the previous example, only dataclasses has a `$ref`, but it can be fully customized. You can use `schema_ref` on any defined types (`NewType`/`class`/`Annotated`/etc.). `schema_ref` argument can be:
- `str` -> this string will be used directly in schema generation
- `...` -> schema generation will use the name of the type
- `None` -> this type will have no `$ref` in schema

```python
{!schema_ref.py!}
```

!!! note
    Actually, there is a small restriction with `NewType`: you cannot put a `schema_ref` if the super type is not a builtin type (`list[...]`/`int`/etc.). 
    
    In fact, `NewType` super type serialization could be affected by different conversions and a same `$ref` would embed different schema.
    
### Default `$ref`

There is a default `schema_ref` for each type; following types get a `...` ref (which means a ref with their name):

- `dataclass`
- `NewType`
- `TypedDict`
- `NamedTuple`
- every types decorated with `schema`

This default behavior is customizable by setting `settings.default_ref` function like this

```python
from apischema import settings
@settings.default_ref
def default_ref(cls):
    return None  # This example remove default ref for every types
``` 

### Ref factory

`schema_ref` is used to set a short ref, like the name of a class, but in schema, `$ref` looks like `#/$defs/Foo`. In fact, schema generation use the ref given by `schema_ref` and pass it to a `ref_factory` function (a parameter of schema generation functions) which will convert it to its final form. [JSON schema version](#json-schemaopenapi-version) comes with its default `ref_factory`, for draft 2019-09, it prefixes the ref with `#/$defs/`, while it prefixes with `#/components/schema` in case of *OpenAPI*.

```python
{!ref_factory.py!}
```

!!! note
    When `ref_factory` is passed in arguments, definitions are not added to the generated schema. That's because `ref_factory` would surely change definitions location, so there would be no interest to add them with a wrong location. This definitions can of course be generated separately with `definitions_schema`.
    
    Passing `ref_factory` also give a default value of `True` for [`all_refs`](#use-ref-only-for-reused-types) parameters.

## JSON schema / *OpenAPI* version

JSON schema has several versions — *OpenAPI* is treated as a JSON schema version. If *Apischema* natively use the last one: draft 2019-09, it is possible to specify a schema version which will be used for the generation.

```python
{!schema_versions.py!}
```

## `readOnly` / `writeOnly`
Dataclasses `InitVar` and `field(init=False)` fields will be flagged respectively with `"writeOnly": true` and `"readOnly": true` in the generated schema.

If deserialization and serialization schemas both appears in `definition_schema`, properties are merged and the resulting schema contains then `readOnly` and `writeOnly` properties. By the way, the `required` is not merged because it can't (it would mess up validation if some not-init field was required), so deserialization `required` is kept because it's more important as it can be used in validation (*OpenAPI* 3.0 semantic which allows the merge [has been dropped](https://www.openapis.org/blog/2020/06/18/openapi-3-1-0-rc0-its-here) in 3.1, so it has not been judged useful to be supported)

## FAQ

#### Why field default value is not used by default to to generate JSON schema?

Actually, default value is not always the usable in the schema, for example `NotNull` fields with a `None` default value. Because `default` keyword is kind of facultative in the schema, it has been decided to not put it by default in order to not put wrong default by accident.
