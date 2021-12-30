# Difference with pydantic

As the question is often asked, it is answered in a dedicated section. Here are some the key differences between *apischema* and *pydantic*:

### *apischema* is (a lot) faster

According to [benchmark](performance_and_benchmark.md), *apischema* is a lot faster than *pydantic*, especially for serialization. Both use Cython to optimize the code, but even without compilation (running only Python modules), *apischema* is still faster than Cythonized *pydantic*.

Better performance, but not at the cost of fewer functionalities; that's rather the opposite: [dynamic aliasing](json_schema.md#dynamic-aliasing-and-default-aliaser), [conversions](conversions.md), [flattened fields](data_model.md#composition-over-inheritance---composed-dataclasses-flattening), etc.

### *apischema* can generate [*GraphQL* schema](graphql/overview.md) from your resolvers

Not just a simple printable schema but a complete `graphql.GraphQLSchema` (using [*graphql-core*](https://github.com/graphql-python/graphql-core/) library) which can be used to execute your queries/mutations/subscriptions through your resolvers, powered by *apischema* (de)serialization and conversions features.

Types and resolvers can be used both in traditional JSON-oriented API and GraphQL API.

### *apischema* uses standard dataclasses and types

*pydantic* uses its own `BaseModel` class, or its own pseudo-`dataclass`, so you are forced to tie all your code to the library, and you cannot easily reuse code written in a more standard way or in external libraries.

By the way, Pydantic use expressions in typing annotations (`conint`, etc.), while it's not recommended and treated as an error by tools like *Mypy*

### *apischema* doesn't require external plugins for editors, linters, etc.

*pydantic* requires a plugin to allow *Mypy* to type check `BaseModel` and other *pydantic* singularities (and to not raise errors on it); plugins are also needed for editors.

### *apischema* doesn't mix up (de)serialization with your code

While *pydantic* mixes up model constructor with deserializer, *apischema* uses dedicated functions for its features, meaning your dataclasses are instantiated normally with type checking. In your code, you manipulate objects; (de)serialization is for input/output.

*apischema* also doesn't mix up validation of external data with your statically checked code; there is no runtime validation in constructors.

### *apischema* truly works out-of-the-box with forward type references (especially for recursive model)

*pydantic* requires calling `update_forward_refs` method on recursive types, while *apischema* "just works".

### *apischema* supports `Generic` in Python 3.6 and without requiring additional stuff

*pydantic* `BaseModel` cannot be used with generic model, you have to use `GenericModel`, and it's not supported in Python 3.6.

With *apischema*, you just write your generic classes normally. 

### *apischema* [conversions](conversions.md) feature allows to support any type defined in your code, but also in external libraries

*pydantic* doesn't make it easy to support external types, like `bson.ObjectId`; see this [issue](https://github.com/tiangolo/fastapi/issues/68) on the subject. You could dynamically add a `__get_validators__` method to foreign classes, but that doesn't work with builtin types like `collection.deque` and other types written in C.

Serialization customization is harder, with definition of encoding function by model; it cannot be done at the same place as deserialization. There is also no correlation done between (de)serialization customization and model JSON schema; you could have to overwrite the generated schema if you don't want to get an inconsistency.

*apischema* only requires a few lines of code to support any type you want, from `bson.ObjectId` to *SQLAlchemy* models by way of builtin and generic like `collection.deque`, and even [*pydantic*](#apischema-supports-pydantic). Conversions are also integrated in JSON schema this one is generated according to the source/target of the conversion

Here is a comparison of a custom type support:

```python
{!pydantic_conversion.py!}
```

### *apischema* can also customize serialization with computed fields

[Serialized methods/properties](de_serialization.md#serialized-methodsproperties) are regular methods/properties which are included in serialization effortlessly.

### *apischema* allows you to use composition over inheritance

[Flattened fields](data_model.md#composition-over-inheritance---composed-dataclasses-flattening) is a distinctive *apischema* feature that is very handy to build complex model from smaller fragments; you don't have to merge the fields of your fragments in a complex class with a lot of fields yourself, *apischema* deal with it for you, and your code is kept simple.

### *apischema* has a functional approach, *pydantic* has an object one

*pydantic* features are based on `BaseModel` methods. You have to have a `BaseModel` instance to do anything, even if you manipulate only an integer. Complex *pydantic* stuff like `__root__` model or deserialization customization come from this approach.

*apischema* is functional, it doesn't use method but simple functions, which works with all types. You can also register conversions for any types similarly you would implement a type class in a functional language. And your class namespace don't mix up with a mandatory base class' one.

### *apischema* can use both *camelCase* and *snake_case* with the same types

While *pydantic* field aliases are fixed at model creation, *apischema* [lets you choose](json_schema.md#dynamic-aliasing-and-default-aliaser) which aliasing you want at (de)serialization time. 

It can be convenient if you need to juggle with cases for the same models between frontends and other backend services for example.

### *apischema* doesn't coerce by default

Your API respects its schema. 

It can also coerce, for example to parse configuration file, and coercion can be adjusted (for example coercing list from comma-separated string). 

### *apischema* has a better integration of JSON schema/OpenAPI

With *pydantic*, if you want to have a `nullable` field in the generated schema, you have to put `nullable` into schema extra keywords.

*apischema* is bound to the last JSON schema version but offers conversion to other version like OpenAPI 3.0 and `nullable` is added for `Optional` types.

*apischema* also supports more advanced features like `dependentRequired` or `unevaluatedProperties`. Reference handling is also more [flexible](json_schema.md#complexrecursive-types---json-schema-definitionsopenapi-components)

### *apischema* can add validators and JSON schema to `NewType`

So it will be used in deserialization validation. You can use `NewType` everywhere, to gain a better type checking, self-documented code.

### *apischema* validators are regular methods with [automatic dependencies management](validation.md#automatic-dependency-management)

Using regular methods allows benefiting of type checking of fields, where *pydantic* validators use dynamic stuff (name of the fields as strings) and are not type-checked or have to get redundant type annotations.

*apischema* validators also have automatic dependency management. And *apischema* directly supports JSON schema [property dependencies](json_schema.md#property-dependencies).

Comparison is simple with an example (validator is taken from [*pydantic* documentation](https://pydantic-docs.helpmanual.io/usage/validators/#root-validators):

```python
{!pydantic_validator.py!}
```

### *apischema* supports *pydantic*

It's not a feature, is just the result of [30 lines of code](examples/pydantic_support.md).
