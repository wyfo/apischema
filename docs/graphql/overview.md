# GraphQL Overview

*Apischema* supports *GraphQL* through [*graphql-core*](https://github.com/graphql-python/graphql-core) library.

You can install this dependency directly with *Apischema* using the following extra requirement:
```shell
pip install apischema[graphql]
```

*GraphQL* supports consists of generating a *GraphQL* schema `graphql.GraphQLSchema` from your data model and endpoints (queries/mutations/subscribtions), in a similar way than the JSON schema generation. This schema can then be used through *graphql-core* library to query/mutate/subscribe.

```python
{!graphql_overview.py!}
```

*GraphQL* is fully integrated with the rest of *Apischema* features, especially [conversions](../conversions.md), so it's easy to integrate ORM and other custom types in the generated schema; this concerns query results but also arguments.

By the way, while *GraphQL* doesn't support constraints, *Apischema* still offers you all the power of its [validation feature](../validation.md). In fact, *Apischema* deserialize and validate all the arguments passed to resolvers. 


## FAQ

#### Is it possible to use the same classes to do both GraphQL and REST-API?
Yes it is. *GraphQL* has some restrictions in comparison to JSON schema (see [next section](data_model_and_resolvers.md)), but this taken in account, all of your code can be reused. In fact, *GraphQL* endpoints can also be used both by a *GraphQL* API and a more traditional REST or RPC API.
