# Conversions – (de)serialization customization

*apischema* covers majority of standard data types, but it's of course not enough, that's why it gives you the way to add support for all your classes and the libraries you use.

Actually, *apischema* uses internally its own feature to support standard library data types like UUID/datetime/etc. (see [std_types.py](https://github.com/wyfo/apischema/blob/master/apischema/std_types.py))

ORM support can easily be achieved with this feature (see [SQLAlchemy example](examples/sqlalchemy_support.md)).

In fact, you can even add support of competitor libraries like *Pydantic* (see [*Pydantic* compatibility example](examples/pydantic_support.md))

## Principle - apischema conversions

An *apischema* conversion is composed of a source type, let's call it `Source`, a target type `Target` and a converter function of signature `(Source) -> Target`.

When a class (actually, a non-builtin class, so not `int`/`list`/etc.) is deserialized, *apischema* will look if there is a conversion where this type is the target. If found, the source type of conversion will be deserialized, then the converter will be applied to get an object of the expected type. Serialization works the same (inverted) way: look for a conversion with type as source, apply then converter, and get the target type.

Conversion can only be applied on classes, not other types like `NewType`, etc. (see [FAQ](#why-conversion-can-only-be-applied-on-classes-and-not-on-others-types-newtype-etc-))

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

On the other hand, deserializers cannot be inherited, because the same `Source` passed to a conversion function `(Source) -> Target` will always give the same `Target` (not ensured to be the desired subtype).

However, there is one way to do it by using a `classmethod` and the special decorator `apischema.conversions.inherited_deserializer`; the class parameter of the method is then assumed to be used to instantiate the return.  

```python
{!deserializer_inheritance.py!}
```

!!! note
    An "other" way to achieve that would be to use `__init_subclass__` method in order to add a deserializer to each subclass. In fact, that's what `inherited_deserializer` is doing behind the scene.

## Conversion object

In previous example, conversions where registered using only converter functions. However, everywhere you can pass a converter, you can also pass a `apischema.conversions.Conversion` instance.
`Conversion` allows to add additional metadata to conversion than a function can do ; it can also be used to precise converter source/target when annotations are not available.

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

By the way, builtin classes are not affected by conversions, this is especially true for containers like `list` or `dict`. Dynamic conversions can thus be used to modify a type inside it's container.

```python
{!local_conversions.py!}
```

### Dynamic conversions interact with `schema_ref`

Dynamic conversions are applied before looking for a ref registered with `schema_ref`

```python
{!dynamic_schema_ref.py!}
```

### Bypass registered conversion

Dynamic conversions can be used to bypass a registered conversion, i.e. to (de)serialize the given type as it would be without conversion registered. It requires to use a `Conversion` object with an `apischema.conversions.identity` converter, and the same source type as the target type.

```python
{!bypass_conversions.py!}
```

## Generic conversions

`Generic` conversions are supported out of the box.

```python
{!generic_conversions.py!}
```

!!! warning
(De)serializer cannot decorate methods of `Generic` classes in Python 3.6, it has to be used outside of class.

However, *apischema* doesn't support conversion of specialized generic like `Foo[bool] -> int` (see [FAQ](#why-conversion-can-only-be-applied-on-classes-and-not-on-others-types-newtype-fooint-etc))

By the way, dynamic generic conversions are also supported.

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

Fields conversions are different of other conversion by the fact they apply directly on the field type and not on a particular class: if field type is a list of `Foo`, the converter will have to take a list in parameter.
However, it's possible with [sub-conversions](#sub-conversions) to get a similar behaviour to normal conversions.

### Generic field conversions

Generic field conversions are again handled naturally out-of-the-box

```python
{!field_generic_conversion.py!}
```

!!! note
As shown in the example, *apischema* will substitute `TypeVar`s according to the field type, even if it has itself a generic type. By the way, LSP is taken in account when field has not the same type as the conversion side (here, `dict` is a subtype of `Mapping`, so type vars can be substituted in a serialization context)

## Sub-conversions

Sub-conversions are quite an advanced use; they are [dynamic conversions](#dynamic-conversions--select-conversions-at-runtime) applied after a conversion (or an other computation, like a serialized method).

```python
{!sub_conversions.py!}
```

Sub-conversions can also be used to [bypass registered conversions](#bypass-registered-conversion).

### Serialized method sub-conversions

Serialized method can also have dedicated sub-conversions

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
# dataclass_model(cls)(make_dataclass(cls.__name__, fields))
dataclass_model(cls)(lambda: make_dataclass(cls.__name__, fields))
```

- [Serialized methods/properties](de_serialization.md#serialized-methodsproperties) of the class are automatically added to the dataclass model (but you can also declare serialized methods in the dataclass model). This behavior can be toggled off using `fields_only` parameter with a `True` value. 

## Default conversions

As almost every default behavior in *apischema*, default conversion can be configured using `apischema.settings.deserialization`/`apischema.settings.serialization`. The initial value of these settings are the function which retrieved conversions registered with `deserializer`/`serializer`.

You can for example [support *attrs*](examples/attrs_support.md) classes with this feature:


```python
{!examples/attrs_support.py!}
```

## FAQ

#### Why conversion can only be applied on classes and not on others types (`NewType`, `Foo[int]`, etc.)?

Serialization doesn't have access to annotations (it's way less performant to use model annotations, and things like `Union` are useless in a serialization point of view), it uses instead the class of the object serialized; so `NewType` and other things that don't exist at runtime are simply unavailable. (As a side effect, serialization conversions applied to a `NewType` super-type will be applied to objects even if they are annotated with `NewType`, but it's a corner case as `NewType` is mainly used with builtin types `int`, `str`, etc.)

Serialization conversions with specialized generic like `Foo[int]` are impossible too, because the generic argument of `Foo` cannot be retrieved. 

On the other hand, deserialization use annotations, so it could indeed apply conversions to other types (and it was in fact the case in the firsts versions).

However, it has been judged better to get the same restriction on both operation for simplicity and because the main need of deserialization customization is validation, which can already be registered for `NewType` or embedded in `Annotated`, etc.

#### Why conversion cannot be applied on primitive type?

It's not a technical issue (it was a performance isssue in the first versions), but rather a design choice to keep things simple.

#### Why dynamic conversion cannot apply on the whole data model?

Actually, it would be to implement global dynamic conversions for (de)serialization. However, when it comes to JSON schema generation, things would get completely messy. In fact, it would break the concept of `$ref`, because the content of a `$ref` would be changed between two endpoints with different global conversions, as conversions could change the fields in one and not in the other. 

