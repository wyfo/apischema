# Conversions – (de)serialization customization

*apischema* covers majority of standard data types, but it's of course not enough, that's why it gives you the way to add support for all your classes and the libraries you use.

Actually, *apischema* uses internally its own feature to support standard library data types like UUID/datetime/etc. (see [std_types.py](https://github.com/wyfo/apischema/blob/master/apischema/std_types.py))

ORM support can easily be achieved with this feature (see [SQLAlchemy example](examples/sqlalchemy_support.md)).

In fact, you can even add support of competitor libraries like *Pydantic* (see [*Pydantic* compatibility example](examples/pydantic_support.md))

## Principle - apischema conversions

An *apischema* conversion is composed of a source type, let's call it `Source`, a target type `Target` and a converter function of signature `(Source) -> Target`.

When a class (actually, a non-builtin class, so not `int`/`list`/etc.) is deserialized, *apischema* will look if there is a conversion where this type is the target. If found, the source type of conversion will be deserialized, then the converter will be applied to get an object of the expected type. Serialization works the same (inverted) way: look for a conversion with type as source, apply then converter, and get the target type.

Conversion can only be applied on classes, not other types like `NewType`, etc. (see [FAQ](#why-dynamic-conversion-cannot-apply-on-the-whole-data-model))

Conversions are also handled in schema generation: for a deserialization schema, source schema is merged to target schema, while target schema is merged to source schema for a serialization schema.


## Register a conversion

Conversion is registered using `apischema.deserializer`/`apischema.serializer` for deserialization/serialization respectively.

When used as function decorator, the `Source`/`Target` types are directly extracted from conversion function signature. 

`serializer` can be called on methods/properties, in which case `Source` type is inferred to be th owning type.

```python
{!conversions.py!}
```

!!! warning
    (De)serializer methods cannot be used with `typing.NamedTuple`; in fact, *apischema* uses `__set_name__` magic method but it is not called on `NamedTuple` subclass fields. 

### Multiple deserializers

Sometimes, you want to have several possibilities to deserialize a type. If it's possible to register a deserializer with an `Union` param, it's not very practical. That's why *apischema* make it possible to register several deserializers for the same type. They will be handled with an `Union` source type (ordered by deserializers registration), with the right serializer selected according to the matching alternative.

```python
{!multiple_deserializers.py!}
```

On the other hand, serializer registration overwrite the previous registration if any. 

`apischema.conversions.reset_deserializers`/`apischema.conversions.reset_serializers` can be used to reset (de)serializers (even those of the standard types embedded in *apischema*)

### Inheritance

All serializers are naturally inherited. In fact, with a conversion function `(Source) -> Target`, you can always pass a subtype of `Source` and get a `Target` in return.

Moreover, when serializer is a method/property, overriding this method/property in a subclass will override the inherited serializer.

```python
{!serializer_inheritance.py!}
```

!!! note
Inheritance can also be toggled off in specific cases, like in the [Class as union of its subclasses](examples/subclasses_union.md) example

On the other hand, deserializers cannot be inherited, because the same `Source` passed to a conversion function `(Source) -> Target` will always give the same `Target` (not ensured to be the desired subtype).

!!! note
Pseudo-inheritance could be achieved by registering a conversion (using for example a `classmethod`) for each subclass in `__init_subclass__` method (or a metaclass), or by using `__subclasses__`; see [example](examples/inherited_deserializer.md)


## Generic conversions

`Generic` conversions are supported out of the box.

```python
{!generic_conversions.py!}
```

!!! warning
    (De)serializer cannot decorate methods of `Generic` classes in Python 3.6, it has to be used outside of class.

However, it's not allowed to register a conversion of a specialized generic type, like `Foo[int]`(see [FAQ](#why-conversion-can-only-be-applied-on-classes-and-not-on-others-types-newtype-fooint-etc)).

## Conversion object

In previous example, conversions where registered using only converter functions. However, everywhere you can pass a converter, you can also pass a `apischema.conversions.Conversion` instance.
`Conversion` allows adding additional metadata to conversion than a function can do ; it can also be used to precise converter source/target when annotations are not available.

```python
{!conversion_object.py!}
```

## Dynamic conversions — select conversions at runtime

No matter if a conversion is registered or not for a given type, conversions can also be provided at runtime, using `conversions` parameter of `deserialize`/`serialize`/`deserialization_schema`/`serialization_schema`.

```python
{!dynamic_conversions.py!}
```

!!! note
    For `definitions_schema`, conversions can be added with types by using a tuple instead, for example `definitions_schema(serializations=[(list[Foo], foo_to_bar)])`. 

`conversions` parameter can also take a list of conversions, when you have a `Union`, a `tuple` or when you want to have several deserializations for the same type


### Dynamic conversions are local

Dynamic conversions are discarded after having been applied (or after class without conversion having been encountered). For example, you can't apply directly a dynamic conversion to a dataclass field when calling  `serialize` on an instance of this dataclass. Reasons of this design are detailed in the [FAQ](#why-dynamic-conversion-cannot-apply-on-the-whole-data-model). 

However, there is an exception for containers like `Collection`, `list`, `dict`, etc. and `Union`, and types with a registered conversion from/to a container: dynamic conversions are not discarded and can be used by their elements 

```python
{!local_conversions.py!}
```

### Dynamic conversions interact with `schema_ref`

Dynamic conversions are applied before looking for a ref registered with `schema_ref`

```python
{!dynamic_schema_ref.py!}
```

### Bypass registered conversion

Using `apischema.conversion.identity` as a dynamic conversion allows to bypass a registered conversion, i.e. to (de)serialize the given type as it would be without conversion registered.

```python
{!bypass_conversions.py!}
```

!!! note
    For a more precise selection of bypassed conversion, for `tuple` or `Union` member for example, it's possible to pass the concerned class as the source *and* the target of conversion *with* `identity` converter, as shown in the example. 

### Liskov substitution principle

LSP is taken in account when applying dynamic conversion: serializer source can be a subclass of the actual class and deserializer target can be a superclass of the actual class.

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

Serialized method can also have dedicated conversions

```python
{!serialized_conversions.py!}
```


## Dataclass model - automatic conversion from/to dataclass

Conversions are a powerful tool, which allows to support every type you need. If it is particularly well suited for scalar types (`datetime.datetime`, `bson.ObjectId`, etc.), it may seem a little bit complex for object types. In fact, the conversion would often be a simple mapping of fields between the type and a dataclass.

That's why *apischema* provides a shortcut for this case: `apischema.conversions.dataclass_model`; it allows to specify a dataclass which will be used as a typed model for a given class : each field of the dataclass will be mapped on the attributes of the class instances.
The function returns two `Conversion` object, one for deserialization and the other for serialization. They can then be registered with `serializer`/`deserializer`, or be used dynamically.

Remember that dataclass can also be declared dynamically with `dataclasses.make_dataclasses`. That's especially useful when it comes to add support for libraries like ORM. The following example show how to add a [basic support for 
*SQLAlchemy*](examples/sqlalchemy_support.md):

```python
{!examples/sqlalchemy_support.py!}
```

There are two differences with regular conversions :

- The dataclass model computation can be deferred until it's needed. This is because some libraries do some resolutions after class definition (for example SQLAchemy resolves dynamic string references in relationships). So you could replace the following line in the example, it would works too.

```python
# dataclass_model(cls, make_dataclass(cls.__name__, fields))
dataclass_model(cls, lambda: make_dataclass(cls.__name__, fields))
```

- [Serialized methods/properties](de_serialization.md#serialized-methodsproperties) of the class are automatically added to the dataclass model (but you can also declare serialized methods in the dataclass model). This behavior can be toggled off using `fields_only` parameter with a `True` value. 

## Function parameters as dataclass

`apischema.conversions.dataclass_input_wrapper` can convert a function into a new function taking a unique parameter, a dataclass whose fields are mapped from the original function parameters.

It can be used for example to build a deserialization conversion from an alternative constructor.

```python
{!dataclass_input_wrapper.py!}
```

!!! note
    Metadata can also be passed with `parameters_metadata` parameter; it takes a mapping of parameter names as key and mapped metadata as value.

## Default conversions

As almost every default behavior in *apischema*, default conversion can be configured using `apischema.settings.deserialization`/`apischema.settings.serialization`. The initial value of these settings are the function which retrieved conversions registered with `deserializer`/`serializer`.

You can for example [support *attrs*](examples/attrs_support.md) classes with this feature:

```python
{!examples/attrs_support.py!}
```

## Sub-conversions

Sub-conversions are [dynamic conversions](#dynamic-conversions--select-conversions-at-runtime) applied on the result of a conversion.

```python
{!sub_conversions.py!}
```

Sub-conversions can also be used to [bypass registered conversions](#bypass-registered-conversion) or to define [recursive conversions](#lazyrecursive-conversions).

## Lazy/recursive conversions

Conversions can be defined lazily, i.e. using a function returning `Conversion` (single, or a collection of it); this function must be wrap into a `apischema.conversions.LazyConversion` instance.

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

#### Why conversion can only be applied on classes?

Serialization doesn't have access to annotations (it's way less performant to use model annotations, and things like `Union` are useless in a serialization point of view), it uses instead the class of the object serialized; so `NewType` and other things that don't exist at runtime are simply unavailable.

Also, generic specialization like `Foo[int]` cannot be retrieved by serialization, that's why their registration is not allowed. 

On the other hand, deserialization use annotations, so it could indeed apply conversions to other types (and it was in fact the case in the firsts versions).

However, it has been judged better to get the same restriction on both operation for simplicity and because the main need of deserialization customization is validation, which can already be registered for `NewType` or embedded in `Annotated`, etc.

#### Why `Annotated` cannot be used to specified conversions?

Same reason than above, because serialization doesn't use type annotations, so conversions would be lost.

Actually, for dataclasses/namedtuples fields, as well as serialized methods return, it would be possible to use read an annotated conversion (only on the field/return type, not on nested types), even during serialization.
However, this behavior could be confusing, because `Annotated[MyType, conversion(...)]` would be allowed as a dataclass fields, but `list[Annotated[Mytype, conversions(...)]]` will not work as expected.

That's why it has been decided that conversions should not be embedded in `Annotated`, to keep things simple.


#### Why dynamic conversion cannot apply on the whole data model?

To ensure consistency and reuse of subschemas with a `$ref`. Indeed, if dynamic conversions were global, different endpoints with or without conversions could have different result for nested classes (because one of its field could be impacted), so these classes could not be referenced consistently with their `$ref`.

