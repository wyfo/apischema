# Data model and resolvers

Almost everything of the [Data model section](../data_model.md) remains valid in *GraphQL* integration.

## Restrictions

### `Union`
Unions are only supported between object types, which means `dataclass` and `NamedTuple` (and some [conversions](../conversions.md)/[dataclass model](../conversions.md#dataclass-model---automatic-conversion-fromto-dataclass)).

More precisely, it's only supported in output schema, not in resolvers arguments.

There are 2 exceptions which can be always be used in `Union`:

- `None`/`Optional`: Types are non-null (marked with an exclamation mark `!` in *GraphQL* schema) by default; `Optional` types however results in normal *GraphQL* types (without `!`).
- `apischema.UndefinedType`: it is simply ignored. It is useful in resolvers, see [following section](#undefined_param_default)
 
### `TypedDict`

`TypedDict` is not supported. In fact, typed dicts are not real classes, so their type can not be checked at runtime, but this is required to disambiguate unions/interfaces.

## Interfaces

Interfaces are simply classes marked with `apischema.graphql.interface` decorator. An object type implements an interface when its class inherits of interface-marked class, or when it has [merged fields](../data_model.md#composed-dataclasses-merging) of interface-marked dataclass.

```python
{!interface.py!}
```

## Resolvers

All `dataclass`/`NamedTuple` fields (excepted [skipped](../data_model.md#skip-dataclass-field)) are resolved with their [alias](../json_schema.md#field-alias) in the *GraphQL* schema.

Custom resolvers can also be added by marking methods with `apischema.graphql.resolver` decorator. Methods can be synchronous or asynchronous (defined with `async def` or returning an `Awaitable`).

Resolvers parameters are included in the schema with their type and their default value (except `apischema.Undefined`).

```python
{!resolver.py!}
```

### Undefined parameter default

In *GraphQL*, non required parameters are forced to be nullable. However, *Apischema* allows to distinguish a `null` input from an input absent, by putting `apischema.Undefined` as parameter default of an `Optional` field. Thus, field will not be required, and a `null` value will result in a `None` argument whereas absent parameter will result in an `apischema.Undefined` argument.

```python
{!undefined_default.py!}
```

