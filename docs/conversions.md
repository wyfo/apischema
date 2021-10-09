# Conversions – (de)serialization customization

*apischema* covers the majority of standard data types, but of course that's not enough, which is why it enables you to add support for all your classes and the libraries you use.

Actually, *apischema* itself uses this conversion feature to provide a basic support for standard library data types like UUID/datetime/etc. (see [std_types.py](https://github.com/wyfo/apischema/blob/master/apischema/std_types.py))

ORM support can easily be achieved with this feature (see [SQLAlchemy example](examples/sqlalchemy_support.md)).

In fact, you can even add support for competitor libraries like *Pydantic* (see [*Pydantic* compatibility example](examples/pydantic_support.md))

## Principle - apischema conversions

An *apischema* conversion is composed of a source type, let's call it `Source`, a target type `Target` and a converter function with signature `(Source) -> Target`.

When a class (actually, a non-builtin class, so not `int`/`list`/etc.) is deserialized, *apischema* will check if there is a conversion where this type is the target. If found, the source type of conversion will be deserialized, then the converter will be applied to get an object of the expected type. Serialization works the same way but inverted: look for a conversion with type as source, apply then converter, and get the target type.

Conversions are also handled in schema generation: for a deserialization schema, source schema is merged to target schema, while target schema is merged to source schema for a serialization schema.


## Register a conversion

Conversion is registered using `apischema.deserializer`/`apischema.serializer` for deserialization/serialization respectively.

When used as function decorator, the `Source`/`Target` types are directly extracted from the conversion function signature. 

`serializer` can be called on methods/properties, in which case `Source` type is inferred to be th owning type.

```python
{!conversions.py!}
```

!!! warning
    (De)serializer methods cannot be used with `typing.NamedTuple`; in fact, *apischema* uses the `__set_name__` magic method but it is not called on `NamedTuple` subclass fields. 

### Multiple deserializers

Sometimes, you want to have several possibilities to deserialize a type. If it's possible to register a deserializer with a `Union` param, it's not very practical. That's why *apischema* make it possible to register several deserializers for the same type. They will be handled with a `Union` source type (ordered by deserializers registration), with the right serializer selected according to the matching alternative.

```python
{!multiple_deserializers.py!}
```

On the other hand, serializer registration overwrites the previous registration if any. 

`apischema.conversions.reset_deserializers`/`apischema.conversions.reset_serializers` can be used to reset (de)serializers (even those of the standard types embedded in *apischema*)

### Inheritance

All serializers are naturally inherited. In fact, with a conversion function `(Source) -> Target`, you can always pass a subtype of `Source` and get a `Target` in return.

Moreover, when serializer is a method/property, overriding this method/property in a subclass will override the inherited serializer.

```python
{!serializer_inheritance.py!}
```

!!! note
Inheritance can also be toggled off in specific cases, like in the [Class as union of its subclasses](examples/subclass_union.md) example

On the other hand, deserializers cannot be inherited, because the same `Source` passed to a conversion function `(Source) -> Target` will always give the same `Target` (not ensured to be the desired subtype).

!!! note
Pseudo-inheritance could be achieved by registering a conversion (using for example a `classmethod`) for each subclass in `__init_subclass__` method (or a metaclass), or by using `__subclasses__`; see [example](examples/inherited_deserializer.md)


## Generic conversions

`Generic` conversions are supported out of the box.

```python
{!generic_conversions.py!}
```

However, you're not allowed to register a conversion of a specialized generic type, like `Foo[int]`.

## Conversion object

In the previous example, conversions were registered using only converter functions. However, it can also be done by passing a `apischema.conversions.Conversion` instance. It allows specifying additional metadata to conversion (see [next sections](#sub-conversions) for examples) and precise converter source/target when annotations are not available.

```python
{!conversion_object.py!}
```

## Dynamic conversions — select conversions at runtime

Whether or not a conversion is registered for a given type, conversions can also be provided at runtime, using the `conversion` parameter of `deserialize`/`serialize`/`deserialization_schema`/`serialization_schema`.

```python
{!dynamic_conversions.py!}
```

!!! note
    For `definitions_schema`, conversions can be added with types by using a tuple instead, for example `definitions_schema(serializations=[(list[Foo], foo_to_bar)])`. 

The `conversion` parameter can also take a tuple of conversions, when you have a `Union`, a `tuple` or when you want to have several deserializations for the same type.


### Dynamic conversions are local

Dynamic conversions are discarded after having been applied (or after class without conversion having been encountered). For example, you can't apply directly a dynamic conversion to a dataclass field when calling `serialize` on an instance of this dataclass. Reasons for this design are detailed in the [FAQ](#whats-the-difference-between-conversion-and-default_conversion-parameters). 

```python
{!local_conversions.py!}
```

!!! note
    Dynamic conversion is not discarded when the encountered type is a container (`list`, `dict`, `Collection`, etc. or `Union`) or a registered conversion from/to a container; the dynamic conversion can then apply to the container elements

### Dynamic conversions interact with `type_name`

Dynamic conversions are applied before looking for a ref registered with `type_name`

```python
{!dynamic_type_name.py!}
```

### Bypass registered conversion

Using `apischema.identity` as a dynamic conversion allows you to bypass a registered conversion, i.e. to (de)serialize the given type as it would be without conversion registered.

```python
{!bypass_conversions.py!}
```

!!! note
    For a more precise selection of bypassed conversion, for `tuple` or `Union` member for example, it's possible to pass the concerned class as the source *and* the target of conversion *with* `identity` converter, as shown in the example. 

### Liskov substitution principle

LSP is taken into account when applying dynamic conversion: the serializer source can be a subclass of the actual class and the deserializer target can be a superclass of the actual class.

```python
{!dynamic_conversions_lsp.py!}
```

### Generic dynamic conversions

`Generic` dynamic conversions are supported out of the box. Also, contrary to registered conversions, partially specialized generics are allowed. 

```python
{!dynamic_generic_conversions.py!}
```

## Field conversions

It is possible to register a conversion for a particular dataclass field using `conversion` metadata.

```python
{!field_conversions.py!}
```

!!! note
    It's possible to pass a conversion only for deserialization or only for serialization

## Serialized method conversions

Serialized methods can also have dedicated conversions for their return

```python
{!serialized_conversions.py!}
```

## String conversions

A common pattern of conversion concerns classes that have a string constructor and a `__str__` method; standard types `uuid.UUID`, `pathlib.Path`, `ipaddress.IPv4Address` are concerned. Using `apischema.conversions.as_str` will register a string-deserializer from the constructor and a string-serializer from the `__str__` method.

```python
{!as_str.py!}
```

!!! note
    Previously mentioned standard types are handled by *apischema* using `as_str`.

## Use `Enum` names

`Enum` subclasses are (de)serialized using values. However, you may want to use enumeration names instead, that's why *apischema* provides `apischema.conversion.as_names` to decorate `Enum` subclasses.

```python
{!as_names.py!}
```

## Object deserialization — transform function into a dataclass deserializer

`apischema.objects.object_deserialization` can convert a function into a new function taking a unique parameter, a dataclass whose fields are mapped from the original function parameters.

It can be used for example to build a deserialization conversion from an alternative constructor.


```python
{!object_deserialization.py!}
```

!!! note
    Parameters metadata can be specified using `typing.Annotated`, or be passed with `parameters_metadata` parameter, which is a mapping of parameter names as key and mapped metadata as value.

## Object serialization — select only a subset of fields

`apischema.objects.object_serialization` can be used to serialize only a subset of an object fields and methods.

```python
{!object_serialization.py!}
```

## Default conversions

As with almost every default behavior in *apischema*, default conversions can be configured using `apischema.settings.deserialization.default_conversion`/`apischema.settings.serialization.default_conversion`. The initial value of these settings are the function which retrieved conversions registered with `deserializer`/`serializer`.

You can for example [support *attrs*](examples/attrs_support.md) classes with this feature:

```python
{!examples/attrs_support.py!}
```

*apischema* functions (`deserialize`/`serialize`/`deserialization_schema`/`serialization_schema`/`definitions_schema`) also have a `default_conversion` parameter to dynamically modify default conversions. See [FAQ](#whats-the-difference-between-conversion-and-default_conversion-parameters) for the difference between `conversion` and `default_conversion` parameters.

## Sub-conversions

Sub-conversions are [dynamic conversions](#dynamic-conversions--select-conversions-at-runtime) applied on the result of a conversion.

```python
{!sub_conversions.py!}
```

Sub-conversions can also be used to [bypass registered conversions](#bypass-registered-conversion) or to define [recursive conversions](#lazyrecursive-conversions).

## Lazy/recursive conversions

Conversions can be defined lazily, i.e. using a function returning `Conversion` (single, or a tuple of it); this function must be wrapped into a `apischema.conversions.LazyConversion` instance.

It allows creating recursive conversions or using a conversion object which can be modified after its definition (for example a conversion for a base class modified by `__init_subclass__`)

It is used by *apischema* itself for the generated JSON schema. It is indeed a recursive data, and the [different versions](json_schema.md#json-schema--openapi-version) are handled by a conversion with a lazy recursive sub-conversion.

```python
{!recursive_conversions.py!}
```

### Lazy registered conversions

Lazy conversions can also be registered, but the deserialization target/serialization source has to be passed too.

```python
{!lazy_registered_conversion.py!}
```


## FAQ

#### What's the difference between `conversion` and `default_conversion` parameters?

Dynamic conversions (`conversion` parameter) exists to ensure consistency and reuse of subschemas referenced (with a `$ref`) in the JSON/*OpenAPI* schema. 

In fact, different global conversions (`default_conversion` parameter) could lead to having a field with different schemas depending on global conversions, so a class would not be able to be referenced consistently. Because dynamic conversions are local, they cannot mess with an object field schema.

Schema generation uses the same default conversions for all definitions (which can have associated dynamic conversion).

`default_conversion` parameter allows having different (de)serialization contexts, for example to map date to string between frontend and backend, and to timestamp between backend services.
