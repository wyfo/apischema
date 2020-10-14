# Conversions – (de)serialization customization

*Apischema* covers majority of standard data types, but it's of course not enough, that's why it gives you the way to add support for all your classes and the libraries you use.

Actually, *Apischema* uses internally its own feature to support standard library data types like UUID/datetime/etc. (see [std_types.py](https://github.com/wyfo/apischema/blob/master/apischema/std_types.py))

ORM support can easily be achieved with this feature (see [SQLAlchemy example](examples/sqlalchemy.md)).

In fact, you can even add support of other "rival" libraries like *Pydantic* (see [*Pydantic* compatibility example](examples/pydantic_compatibility.md))

## Principle - *Apischema* conversions

An *Apischema* conversion is composed of a source type, let's call it `Source`, a target type `Target` and a function of signature `(Source) -> Target`.

When a type (actually, a non-builtin type, so not `int`/`list[str]`/etc.) is deserialized, *Apischema* will look if there is a conversion where this type is the target. If found, the source type of conversion will be deserialized, then conversion function will be applied to get an object of the expected type. Serialization works the same (inverted) way: look for a conversion with type as source, apply conversion (normally get the target type).

Conversions are also handled in schema generation: for a deserialization schema, source schema is used (after merging target schema annotations) while target schema is used (after merging source schema annotations) for a serialization schema.

## Register a conversion

Conversion is registered using `deserializer`/`serializer` for deserialization/serialization respectively.

When used as a decorator, the `Source`/`Target` types are directly extracted from conversion function signature. They can also be passed as argument when the function has no type annotations (builtins like `datetime.isoformat` or foreign library functions).

Methods can be used for `serializer`, as well as `classmethod`/`staticmethod` for both (especially `deserializer`) 

```python
{!conversions.py!}
```

### Multiple deserializers

Sometimes, you want to have several possibilities to deserialize a type. If it's possible to register a deserializer with an `Union` param, it's not very practical. That's why *Apischema* make it possible to register several deserializers for the same type. They will be handled with an `Union` source type (ordered by deserializers registration), with the right serializer selected according to the matching alternative.

```python
{!multiple_deserializers.py!}
```

!!! note
    If it seems that the deserializer declared is equivalent to `deserializer(datetime.fromtimestamp, int, datetime)`, there is actually a slight difference: in the example, the deserializer makes 2 function calls (`datetime_from_timestamp` and `datetime.fromtimestamp`) while the second inlined form imply only one function call to `datetime.fromtimestamp`.
    
    In Python, function calls are heavy, so it's good to know. 

On the other hand, serializer registration overwrite the previous registration if any. That's how the default serialization of builtin types like `datetime` can be modified (because it's just a `serializer` call in *Apischema* code).

This is not possible to overwrite this way deserializers (because they stack), but `reset_deserializers` can be used to reset them before adding new ones. Also, `self_deserializer` can be used to add a class itself as a deserializer (when it's a supported type like a dataclass).

### Inheritance

All serializers are naturally inherited. In fact, with a conversion function `(Source) -> Target`, you can always pass a subtype of `Source` and get a `Target` in return.

Moreover, when serializer is a method (and no `param` is passed to `serializer`, overriding this method in a subclass will override the inherited serializer.

```python
{!serializer_inheritance.py!}
```

On the other hand, deserializers cannot be inherited, because the same `Source` passed to a conversion function `(Source) -> Target` will always give the same `Target` (not ensured to be the desired subtype).

However, there is one way to do it by using a `classmethod` and the special decorator `inherited_deserializer`; the class parameter of the method is then assumed to be used to instantiate the return.  

```python
{!deserializer_inheritance.py!}
```

!!! note
    An "other" way to achieve that would be to use `__init_subclass__` method in order to add a deserializer to each subclass. In fact, that's what `inherited_deserializer` is doing behind the scene.

## Extra conversions - choose the conversion you want

Conversion is a powerful feature, but, registering only one (de)serialization by type may not be enough. Some types may have different representations, or you may have different serialization for a given entity with more or less data (for example a "simple" and a "detailed" view). Hopefully, *Apischema* let you register as many conversion as you want for your classes and gives you the possibility to select the one you want.
 
Conversions registered with `deserializer`/`serializer` are the default ones, they are selected when no conversion is precised. Other conversions are registered `extra_deserializer`/`extra_serializer` (they have the same signature than the previous ones).

Conversions can then be selected using the `conversions` parameter of *Apischema* functions `deserialize`/`serialize`/`deserialization_schema`/`serialization_schema`. This parameter must be mapping of types:

- for deserialization, target as key and source(s) as value
- for serialization, source as key and target as value

(Actually, the type for which is registered the conversion is in key) 
For deserialization, if there is [several possible source](#multiple-deserializers), `conversions` values can also be a collection of types. It will again result in a `Union` deserialization.

!!! note
    For `definitions_schema`, conversions can be added with types by using a tuple instead, for example `definitions_schema(serializations=[(list[Foo], {Foo: Bar})])`. 
    
```python
{!extra_de_serializer.py!}
```

### Chain conversions

Conversions mapping put in `conversions` parameter is not used in all the deserialization/serialization. In fact it is "reset" as soon as a non-builtin type (so, not `int`/`list[int]`/`NewType` instances/etc.) is encountered. Not having this reset would completely break the possibility to have `$ref` in generated schema, because a `conversions` could then change the serialization of a field of a dataclass in one particular schema but not in another (and bye-bye *OpenAPI* components schema).

But everything is not lost. Let's illustrate with an example. As previously mentioned, *Apischema* uses its own feature internally at several places. One of them is schema generation. JSON schema is generated using an internal `JsonSchema` type, and is then serialized; the JSON schema version selection result in fact in a conversion that is selected according to the version (by `JsonSchemaVersion.conversions` property). However, JSON schema is recursive and the serialization of `JsonSchema` returns a dictionary which can contain other `JsonSchema` ... but it has been written above that `conversions` is reset.

That's why `deserializer` and others conversion registers have a `conversions` parameter that will be taken as the new `conversions` after the conversion application. In JSON schema example, it allows sub-`JsonSchema` to be serialized with the correct `conversions`. The following example is extracted from [*Apischema* code](https://github.com/wyfo/apischema/blob/master/apischema/json_schema/versions.py):

```python
{!chain_conversions.py!}
```

### Field conversions

Dataclass fields conversions can also be customized using `conversions` metadata. 

```python
{!field_conversions.py!}
```

`conversions` metadata can also be used to add directly a (de)serializer to a field — `deserialization` and `serialization` are then applied after the (de)serializer as [chained conversions](#chain-conversions)

```python
{!field_de_serializer.py!}
```

## Generic conversions

`Generic` conversions are supported out of the box. However, keep in mind that serialization doesn't use type model, so they will not be used in serialization, but will be used on the other hand in serialization schema generation.

```python
{!generic_conversions.py!}
```

!!! warning
    As shown in example, methods of `Generic` classes are not handled before 3.7
    
!!! note
    *Apischema* doesn't support specialization of `Generic` conversion like `Foo[bool] -> int`.


## That's not all

Also not (yet) presented in this section : *raw deserializers*, *dataclass serializers* and *global default (de)serialization*.

## FAQ

#### Why conversions parameter is a mapping and not just a tuple? Are there any cases where it can be several conversions at the same time?
Tuples (and unions in case of deserialization)