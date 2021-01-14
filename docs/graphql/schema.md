# GraphQL schema

*GraphQL* schema is generated by passing all the operations (query/mutation/subscription) functions to `apischema.graphql.graphql_schema`. 

Functions parameters and return types are then processed by *Apischema* to generate the `Query`/`Mutation`/`Subscription` types with their resolvers/subscribers, which are then passed to `graphql.GraphQLSchema`.

In fact, `graphql_schema` is just a wrapper around `graphql.GraphQLSchema` (same parameters plus a few extras); it just uses *Apischema* abstraction to build `GraphQL` object types directly from your code. 

## Operations

*GraphQL* operations can be passed to `graphql_schema` either using simple functions or using `apischema.graphql.Operation`. This wrapper has the same interface as `apischema.graphql.resolver` (alias, error handler, etc.)

## *camelCase*

*GraphQL* use *camelCase* as a convention for resolvers; *Apischema* follows this convention by automatically convert all resolver names (and their parameters) to *camelCase*. `graphql_schema` has an `aliaser` parameter if you want to use another case.

## Type names

Schema types are named the same way they are in generated JSON schema: type name is used by default, and it can be overridden using [`apischema.schema_ref`](../json_schema.md#customize-ref)

```python
{!graphql_schema_ref.py!}
```

However, in *GraphQL* schema, unions must be named, so `typing.Union` used should be annotated with `apischema.schema_ref`. `graphql_schema` also provides a `union_ref` parameter which can be passed as a function to generate a type name from the union argument. Default `union_ref` is `"Or".join` meaning `typing.Union[Foo, Bar]` will result in `union FooOrBar = Foo | Bar`

```python
{!union_ref.py!}
```


## Additional types

*Apischema* will only include in the schema the types annotating resolvers. However, it is possible to add other types by using the `types` parameter of `graphql_schema`. This is especially useful to add interface implementations where only interface is used in resolver types. 

```python
{!additional_types.py!}
```

## Subscriptions

Subscriptions are particular operations which must return an `AsyncIterable`; this event generator can come with a dedicated resolver to post process the event.

### Event generator only

```python
{!subscription.py!}
```

!!! note
`Operation` can be used instead of a raw function, but error_handler will be ignored for subscription.

### Event generator + resolver

A resolver can be added by passing a tuple `(event_generator, resolver)`.  In this case, *Apischema* will map subscription name, parameters and return type on the resolver instead of the event generator.

The first resolver argument will be the event yielded by the event generator.

```python
{!subscription_resolve.py!}
```

!!! note
    Because this is the resolver who carries additional information, `Operation` has to be used on it and not on the event generator 