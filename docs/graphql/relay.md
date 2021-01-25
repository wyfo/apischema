# Relay

*apischema* provides some facilities to implement a *GraphQL* server following [*Relay* *GraphQL* server specification](https://relay.dev/docs/en/graphql-server-specification). They are included in the module `apischema.graphql.relay`.

!!! note
    These facilities are independent of each others — you could keep only mutations part and use your own identification and connection system for example.


## (Global) Object Identification

*apischema* defines a generic `relay.Node[Id]` interface which can be used which can be used as base class of all identified resources. This class contains a unique generic field of type `Id`, which will be automatically converted into an `ID!` in the schema. The `Id` type chosen has to be serializable into a string-convertible value (it can register [conversions](../conversions.md) if needed).

Each node has to implement the `classmethod` `get_by_id(cls: type[T], id: Id, info: graphql.GraphQLResolveInfo=None) -> T`.

All nodes defined can be retrieved using `relay.nodes`, while the `node` query is defined as `relay.node`. `relay.nodes()` can be passed to `graphql_schema` [`types` parameter](schema.md#additional-types) in order to add them in the schema even if they don't appear in any resolvers.


```python
{!relay_node.py!}
```

!!! warning
    For now, even if its result is note used, `relay.nodes` must be called before generating the schema.

### Global ID

*apischema* defines a `relay.GlobalId` type with the following signature :

```python
@dataclass
class GlobalId(Generic[Node]):
    id: str
    node_class: type[Node]
```
In fact, it is `GlobalId` type which is serialized and deserialized as an `ID!`, not the `Id` parameter of the `Node` class; *apischema* automatically add a [field converter](../conversions.md#field-conversions) to make the conversion between the `Id` (for example an `UUID`) of a given node and the corresponding `GlobalId`.

Node instance global id can be retrieved with `global_id` property.

```python
{!relay_global_id.py!}
```

### Id encoding

*Relay* specifications encourage the use of base64 encoding, so *apischema* defines a `relay.base64_encoding` that you can pass to `graphql_schema` `id_encoding` parameter.

## Connections

*apischema* provides a generic `relay.Connection[Node, Cursor, Edge]` type, which can be used directly without subclassing it; it's also possible to subclass it to add fields to a given connection (or to all the connection which will subclass the subclass). `relay.Edge[Node, Cursor]` can also be subclassed to add fields to the edges.

`Connection` dataclass has the following declaration:
```python
@dataclass
class Connection(Generic[Node, Cursor, Edge]):
    edges: Optional[Sequence[Optional[Edge]]]
    has_previous_page: bool = field(default=False, metadata=skip)
    has_next_page: bool = field(default=False, metadata=skip)
    start_cursor: Optional[Cursor] = field(default=None, metadata=skip)
    end_cursor: Optional[Cursor] = field(default=None, metadata=skip)

    @resolver
    def page_info(self) -> PageInfo[Cursor]:
        ...
```

The `pageInfo` field is computed by a resolver; it uses the cursors of the first and the last edge when they are not provided.

Here is an example of `Connection` use:

```python
{!relay_connection.py!}
```

### Custom connections/edges

Connections can be customizes by simply subclassing `relay.Connection` class and adding the additional fields.

For the edges, `relay.Edge` can be subclassed too, and the subclass has then to be passed as type argument to the generic connection.


```python
{!relay_connection_subclass.py!}
```

## Mutations

*Relay* compliant mutations can be declared with a dataclass subclassing the `relay.Mutation` class; its fields will be put in the payload type of the mutation.

This class must implement a `classmethod`/`staticmethod` name `mutate`; it can be synchronous or asynchronous. The arguments of the method will correspond to the input type fields.

The mutation will be named after the name of the mutation class.

All the mutations declared can be retrieved with `relay.mutations`, in order to be passed to `graphql_schema`.

```python
{!relay_mutation.py!}
```

### ClientMutationId

As you can see in the previous example, the field named `clientMutationId` is automatically added to the input and the payload types. 

The forward of the mutation id from the input to the payload is automatically handled. It's value can be accessed by declaring a parameter of type `relay.ClientMutationId` — even if the parameter is not named `client_mutation_id`, it will be renamed internally.

This feature is controlled by a `Mutation` class variable `_client_mutation_id`, with 3 possible values:

- `None` (automatic, the default): `clientMutationId` field will be nullable unless it's declared as a required parameter (without default value) in the `mutate` method.
- `False`: their will be no `clientMutationId` field added (having a dedicated parameter will raise an error)
- `True`: `clientMutationId` is added and forced to be non-null.

```python
{!relay_client_mutation_id.py!}
```

### Error handling and other resolver arguments

*Relay* mutation are [operations](schema.md#operations), so they can be configured with the same parameters. As they are declared as classes, parameters will be passed as class variables, prefixed by `_` (`error_handler` becomes `_error_handler`)

!!! note
    Because parameters are class variables, you can reuse them by setting their value in a base class; for example, to share a same `error_handler` in a group of mutations.


