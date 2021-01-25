# Data model and resolvers

Almost everything of the [Data model section](../data_model.md) remains valid in *GraphQL* integration.

## Restrictions

### `TypedDict`

`TypedDict` is not supported in output type. In fact, typed dicts are not real classes, so their type can not be checked at runtime, but this is required to disambiguate unions/interfaces.

### `Union`
Unions are only supported between **output** object type, which means `dataclass` and `NamedTuple` (and [conversions](../conversions.md)/[dataclass model](../conversions.md#dataclass-model---automatic-conversion-fromto-dataclass)).

There are 2 exceptions which can be always be used in `Union`:

- `None`/`Optional`: Types are non-null (marked with an exclamation mark `!` in *GraphQL* schema) by default; `Optional` types however results in normal *GraphQL* types (without `!`).
- `apischema.UndefinedType`: it is simply ignored. It is useful in resolvers, see [following section](#undefined_param_default)
 

## Non-null

Types are assumed to be non-null by default, as in Python typing. Nullable types are obtained using `typing.Optional` (or `typing.Union` with a `None` argument).

!!! note
    There is one exception, when resolver parameter default value is not serializable (and thus cannot be included in the schema), parameter type is then set as nullable to make the parameter non-required. For example parameters not `Optional` but with `Undefined` default value will be marked as nullable. This is only for the schema, default value is still used at execution.

## Interfaces

Interfaces are simply classes marked with `apischema.graphql.interface` decorator. An object type implements an interface when its class inherits of interface-marked class, or when it has [merged fields](../data_model.md#composed-dataclasses-merging) of interface-marked dataclass.

```python
{!interface.py!}
```

## Resolvers

All `dataclass`/`NamedTuple` fields (excepted [skipped](../data_model.md#skip-dataclass-field)) are resolved with their [alias](../json_schema.md#field-alias) in the *GraphQL* schema.

Custom resolvers can also be added by marking methods with `apischema.graphql.resolver` decorator — resolvers share a common interface with [`apischema.serialized`](../de_serialization.md#serialized-methodsproperties), with a few differences.

Methods can be synchronous or asynchronous (defined with `async def` or annotated with an `typing.Awaitable` return type).

Resolvers parameters are included in the schema with their type, and their default value.

```python
{!resolver.py!}
```

!!! note
    Contrary to [serialized methods](../de_serialization.md#serialized-methodsproperties), resolver cannot return `Undefined`.

### `GraphQLResolveInfo` parameter

Resolvers can have an additional parameter of type [`graphql.GraphQLResolveInfo`](https://graphql-core-3.readthedocs.io/en/latest/modules/type.html?highlight=GraphQLResolveInfo#graphql.type.GraphQLResolveInfo) (or `Optional[graphql.GraphQLResolveInfo]`), which is automatically injected when the resolver is executed in the context of a *GraphQL* request. This parameter contains the info about the current *GraphQL* request being executed.

### Undefined parameter default — `null` vs. `undefined`

`Undefined` can be used as default value of resolver parameters. It can be to distinguish a `null` input from an absent/`undefined` input. In fact, `null` value will result in a `None` argument where no value will use the default value, `Undefined` so.

```python
{!undefined_default.py!}
```

#### Error handling

Errors occurring in resolvers can be caught in a dedicated error handler registered with `error_handler` parameter. This function takes in parameters the exception, the object, the [info](#graphqlresolveinfo-parameter) and the *kwargs* of the failing resolver; it can return a new value or raise the current or another exception — it can for example be used to log errors without throwing the complete serialization.

The resulting serialization type will be a `Union` of the normal type and the error handling type ; if the error handler always raises, use [`typing.NoReturn`](https://docs.python.org/3/library/typing.html#typing.NoReturn) annotation.

`error_handler=None` correspond to a default handler which only return `None` — exception is thus discarded and the resolver type becomes `Optional`.

The error handler is only executed by *apischema* serialization process, it's not added to the function, so this one can be executed normally and raise an exception in the rest of your code.

Error handler can be synchronous or asynchronous.

```python
{!resolver_error.py!}
```

## ID type
*GraphQL* `ID` has no precise specification and is defined according API needs; it can be a UUID or and ObjectId, etc.

`apischema.graphql_schema` has a parameter `id_types` which can be used to define which types will be marked as `ID` in the generated schema. Parameter value can be either a collection of types (each type will then be mapped to `ID` scalar), or a predicate returning if the given type must be marked as `ID`.

```python
{!id_type.py!}
```

!!! note
    `ID` type could also be identified using `typing.Annotated` and a predicate looking into annotations.

*apischema* also provides a simple `ID` type with `apischema.graphql.ID`. It is just defined as a `NewType` of string, so you can use it when you want to manipulate raw `ID` strings in your resolvers.


### ID encoding

`ID` encoding can directly be controlled the `id_encoding` parameters of `graphql_schema`. A current practice is to use *base64* encoding for `ID`.

```python
{!id_conversion.py!}
```

!!! note
    You can also use `relay.base64_encoding` (see [next section](relay.md#id-encoding))

!!! note
    `ID` serialization (respectively deserialization) is applied **after** *apischema* conversions (respectively before *apischema* conversion): in the example, uuid is already converted into string before being passed to `id_serializer`.

    If you use base64 encodeing and an ID type which is converted by *apischema* to a base64 str, you will get a double encoded base64 string
