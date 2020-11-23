# GraphQL Overview

*Apischema* supports *GraphQL* through [*graphql-core*](https://github.com/graphql-python/graphql-core) library.

You can install this dependency directly with *Apischema* using the following extra requirement:
```shell
pip install apischema[graphql]
```

*GraphQL* supports consists of generating a *GraphQL* schema `graphql.GraphQLSchema` from your data model, in a similar way than the JSON schema generation. This schema can then be used through *graphql-core* library to query/mutate/subscribe.

```python
{!graphql/overview.py!}
```

*GraphQL* feature is fully integrated with the rest of *Apischema* features, especially [conversions](../conversions.md); that means the same way you can automatically handle your ORM classes or other custom types in JSON (de)serialization, these classes can thus be automatically handle in your GraphQLSchema (and its resolvers)

## FAQ

#### GraphQL schema doesn't define constraints; does *Apischema* validate the data received in query/mutation/subscriptions?

Yes. The validation feature presented in [validation section](../validation.md) is fully integrated with *GraphQL*. In fact, *Apischema* use a little wrapper for each resolver in which it deserializes and validates the arguments according to the resolver arguments types.  

