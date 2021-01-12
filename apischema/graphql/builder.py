import warnings
from collections import ChainMap
from contextlib import suppress
from dataclasses import Field, InitVar, dataclass, field as field_, replace
from enum import Enum
from inspect import Parameter, iscoroutinefunction
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Callable,
    Collection,
    Dict,
    Generic,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import graphql

from apischema import serialize
from apischema.aliases import Aliaser
from apischema.conversions import Conversions, Deserialization, Serialization
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.dataclass_utils import (
    get_alias,
    get_default,
    get_field_conversion,
    get_fields,
    is_required,
)
from apischema.graphql.interfaces import get_interfaces, is_interface
from apischema.graphql.resolvers import (
    Resolver,
    get_resolvers,
    none_error_handler,
    resolver_parameters,
    resolver_resolve,
)
from apischema.json_schema.refs import get_ref, schema_ref
from apischema.json_schema.schema import Schema, get_schema, merge_schema
from apischema.metadata.keys import (
    MERGED_METADATA,
    PROPERTIES_METADATA,
    SCHEMA_METADATA,
    check_metadata,
)
from apischema.serialization.serialized_methods import ErrorHandler
from apischema.skip import filter_skipped
from apischema.types import AnyType, NoneType
from apischema.typing import get_args, get_origin
from apischema.utils import Undefined, is_hashable, to_camel_case, type_name

JsonScalar = graphql.GraphQLScalarType(
    "JSON",
    specified_by_url="http://www.ecma-international.org/publications/files/ECMA-ST/ECMA-404.pdf",  # noqa: E501
)
GRAPHQL_PRIMITIVE_TYPES = {
    int: graphql.GraphQLInt,
    float: graphql.GraphQLFloat,
    str: graphql.GraphQLString,
    bool: graphql.GraphQLBoolean,
}


class MissingRef(Exception):
    pass


class Nullable(Exception):
    pass


def ref_or_name(cls: AnyType) -> str:
    return get_ref(cls) or type_name(cls)


T = TypeVar("T")
Lazy = Callable[[], T]
Thunk = Union[Callable[[], T], T]


def exec_thunk(thunk: Thunk[graphql.GraphQLType], *, non_null=None) -> Any:
    result = thunk if isinstance(thunk, graphql.GraphQLType) else thunk()
    if non_null is True and not isinstance(result, graphql.GraphQLNonNull):
        return graphql.GraphQLNonNull(result)  # type: ignore
    if non_null is False and isinstance(result, graphql.GraphQLNonNull):
        return result.of_type
    return result


@dataclass(frozen=True)
class ObjectField:
    name: str
    type: AnyType
    alias: Optional[str] = None
    conversions: Optional[Conversions] = None
    default: Any = graphql.Undefined
    parameters: Optional[Tuple[Collection[Parameter], Mapping[str, AnyType]]] = None
    required: InitVar[bool] = False
    resolve: Optional[Callable] = None
    schema: InitVar[Optional[Schema]] = None
    subscribe: Optional[Callable] = None
    deprecated: Optional[str] = field_(init=False, default=None)
    description: Optional[str] = field_(init=False, default=None)

    def __post_init__(self, required: bool, schema: Optional[Schema]):
        if required:
            object.__setattr__(self, "default", graphql.Undefined)
        if schema is not None and schema.annotations is not None:
            object.__setattr__(self, "description", schema.annotations.description)
            if schema.annotations.deprecated is True:
                object.__setattr__(
                    self, "deprecated", graphql.DEFAULT_DEPRECATION_REASON
                )
            elif isinstance(schema.annotations.deprecated, str):
                object.__setattr__(self, "deprecated", schema.annotations.deprecated)
            if schema.annotations.default is not Undefined and not required:
                object.__setattr__(self, "default", schema.annotations.default)


IdPredicate = Callable[[AnyType], bool]
UnionRefFactory = Callable[[Sequence[str]], str]


class SchemaBuilder(ConversionsVisitor[Conv, Thunk[graphql.GraphQLType]]):
    def __init__(
        self,
        aliaser: Optional[Aliaser],
        is_id: Optional[IdPredicate],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__()
        self.aliaser = aliaser or (lambda s: s)
        self.is_id = is_id or (lambda t: False)
        self.union_ref_factory = union_ref_factory
        self._cache: Dict[Any, Thunk[graphql.GraphQLType]] = {}
        self._non_null = True
        self._ref: Optional[str] = None
        self._schema: Optional[Schema] = None

    @property
    def _description(self) -> Optional[str]:
        if self._schema is not None and self._schema.annotations is not None:
            return self._schema.annotations.description
        else:
            return None

    @property
    def _ref_and_desc(self) -> Tuple[str, Optional[str]]:
        if self._ref is None:
            raise MissingRef
        return self._ref, self._description

    def annotated(
        self, cls: AnyType, annotations: Sequence[Any]
    ) -> Thunk[graphql.GraphQLType]:
        for annotation in annotations:
            if isinstance(annotation, schema_ref):
                annotation.check_type(cls)
                ref = annotation.ref
                if not isinstance(ref, str):
                    raise ValueError("Annotated schema_ref can only be str")
                self._ref = self._ref or ref
            if isinstance(annotation, Schema):
                self._schema = merge_schema(annotation, self._schema)
        return self.visit_with_schema(cls, self._ref, self._schema)

    def any(self) -> Thunk[graphql.GraphQLType]:
        return JsonScalar

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Thunk[graphql.GraphQLType]:
        value_thunk = self.visit(value_type)
        return lambda: graphql.GraphQLList(exec_thunk(value_thunk))

    def _object_field(self, field: Field, field_type: AnyType) -> ObjectField:
        field_type, conversions, _ = get_field_conversion(
            field, field_type, self.operation
        )
        default: Any = graphql.Undefined
        if not is_required(field):
            with suppress(Exception):
                default = serialize(get_default(field), conversions=conversions)
        return ObjectField(
            field.name,
            field_type,
            alias=get_alias(field),
            conversions=conversions,
            default=default,
            required=is_required(field),
            schema=field.metadata.get(SCHEMA_METADATA),
        )

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Thunk[graphql.GraphQLType]:
        types = dict(types)
        object_fields: List[ObjectField] = []
        merged_types: Dict[str, Thunk[graphql.GraphQLType]] = {}
        for field in get_fields(fields, init_vars, self.operation):
            check_metadata(field)
            metadata = field.metadata
            if MERGED_METADATA in metadata:
                field_type, conversions, _ = get_field_conversion(
                    field, types[field.name], self.operation
                )
                with self._replace_conversions(conversions):
                    merged_types[field.name] = self.visit(field_type)
            elif PROPERTIES_METADATA in metadata:
                continue
            else:
                object_fields.append(self._object_field(field, types[field.name]))
        return self.object(cls, object_fields, merged_types)

    def enum(self, cls: Type[Enum]) -> Thunk[graphql.GraphQLType]:
        return self.literal([elt.value for elt in cls])

    def generic(self, cls: AnyType) -> Thunk[graphql.GraphQLType]:
        self._ref = self._ref or get_ref(cls)
        if self._ref is None:
            raise MissingRef
        return super().generic(cls)

    def literal(self, values: Sequence[Any]) -> Thunk[graphql.GraphQLType]:
        if not all(isinstance(v, str) for v in values):
            raise TypeError("Apischema GraphQL only support Enum/Literal of strings")
        name, description = self._ref_and_desc
        return graphql.GraphQLEnumType(
            name, dict(zip(values, values)), description=description
        )

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Thunk[graphql.GraphQLType]:
        try:
            name, description = self._ref_and_desc
            return graphql.GraphQLScalarType(name, description=description)
        except MissingRef:
            return JsonScalar

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> Thunk[graphql.GraphQLType]:
        fields = []
        for field_name, field_type in types.items():
            default = graphql.Undefined
            if field_name in defaults:
                with suppress(Exception):
                    default = serialize(defaults[field_name])
            fields.append(
                ObjectField(
                    field_name,
                    field_type,
                    default=default,
                    required=field_name in defaults,
                )
            )
        return self.object(cls, fields)

    def new_type(self, cls: Type, super_type: AnyType) -> Thunk[graphql.GraphQLType]:
        return self.visit_with_schema(super_type, self._ref, self._schema)

    def object(
        self,
        cls: Type,
        fields: Collection[ObjectField],
        merged_types: Mapping[str, Thunk[graphql.GraphQLType]] = None,
    ) -> Thunk[graphql.GraphQLType]:
        raise NotImplementedError()

    def primitive(self, cls: Type) -> Thunk[graphql.GraphQLType]:
        if cls is NoneType:
            raise Nullable
        try:
            name, description = self._ref_and_desc
            return graphql.GraphQLScalarType(name, description=description)
        except MissingRef:
            return GRAPHQL_PRIMITIVE_TYPES[cls]

    def tuple(self, types: Sequence[AnyType]) -> Thunk[graphql.GraphQLType]:
        raise TypeError("Tuple are not supported")

    def union(self, alternatives: Sequence[AnyType]) -> Thunk[graphql.GraphQLType]:
        alternatives = list(filter_skipped(alternatives, schema_only=True))
        results = []
        for alt in alternatives:
            try:
                results.append(self.visit(alt))
            except Nullable:
                self._non_null = False
        if not results:
            raise TypeError("Empty union")
        return self._union_result(results)

    def visit_with_schema(
        self, cls: AnyType, ref: Optional[str], schema: Optional[Schema]
    ) -> Thunk[graphql.GraphQLType]:
        if self.is_id(cls):
            return graphql.GraphQLNonNull(graphql.GraphQLID)
        if is_hashable(cls) and not self.is_extra_conversions(cls):
            ref, schema = ref or get_ref(cls), merge_schema(get_schema(cls), schema)
        else:
            schema, ref = None, None
        ref_save, schema_save, non_null_save = self._ref, self._schema, self._non_null
        self._ref, self._schema, self._non_null = ref, schema, True
        try:
            result = super().visit(cls)
            non_null = self._non_null
            return lambda: exec_thunk(result, non_null=non_null)
        except MissingRef:
            raise TypeError(f"Missing ref for type {cls}")
        finally:
            self._ref, self._schema = ref_save, schema_save
            self._non_null = non_null_save

    def visit_not_conversion(self, cls: AnyType) -> Thunk[graphql.GraphQLType]:
        key = self._resolve_type_vars(cls), self._ref, self._schema
        if key in self._cache:
            return self._cache[key]
        cache = None

        def rec_sentinel() -> graphql.GraphQLType:
            assert cache is not None
            return cache

        self._cache[key] = rec_sentinel
        try:
            cache = exec_thunk(super().visit_not_conversion(cls))
        except Exception:
            del self._cache[key]
            raise
        else:
            return cache

    def visit(self, cls: AnyType) -> Thunk[graphql.GraphQLType]:
        return self.visit_with_schema(cls, None, None)


def deref_merged_field(
    merged_attr: str, field: graphql.GraphQLField
) -> graphql.GraphQLField:
    def resolve(obj, info, **kwargs):
        return field.resolve(getattr(obj, merged_attr), info, **kwargs)

    return graphql.GraphQLField(**ChainMap(dict(resolve=resolve), field.to_kwargs()))


FieldType = TypeVar("FieldType", graphql.GraphQLInputField, graphql.GraphQLField)


def merge_fields(
    cls: Type,
    fields: Mapping[str, Lazy[FieldType]],
    merged_types: Mapping[str, Thunk[graphql.GraphQLType]],
    merged_field_modifier: Callable[[str, FieldType], FieldType] = None,
) -> Dict[str, FieldType]:
    all_merged_fields: Dict[str, FieldType] = {}
    for merged_name, merged_thunk in merged_types.items():
        merged_type = exec_thunk(merged_thunk, non_null=False)
        if not isinstance(
            merged_type,
            (
                graphql.GraphQLObjectType,
                graphql.GraphQLInterfaceType,
                graphql.GraphQLInputObjectType,
            ),
        ):
            raise TypeError(
                f"Merged field {cls.__name__}.{merged_name} must have an object type"
            )
        merged_fields: Mapping[str, FieldType] = merged_type.fields
        if merged_fields.keys() & all_merged_fields.keys() & fields.keys():
            raise TypeError(f"Conflict in merged fields of {cls}")
        if merged_field_modifier:
            merged_fields = {
                name: merged_field_modifier(merged_name, field)
                for name, field in merged_fields.items()
            }
        all_merged_fields.update(merged_fields)
    return {**{name: field() for name, field in fields.items()}, **all_merged_fields}


class InputSchemaBuilder(
    DeserializationVisitor[Thunk[graphql.GraphQLType]],
    SchemaBuilder[Deserialization],
):
    def _field(self, field: ObjectField) -> Tuple[str, Lazy[graphql.GraphQLInputField]]:
        field_type = self.visit_with_conversions(field.type, field.conversions)
        return self.aliaser(
            field.alias or field.name
        ), lambda: graphql.GraphQLInputField(
            exec_thunk(field_type),
            default_value=field.default,
            description=field.description,
            out_name=field.name,
        )

    def object(
        self,
        cls: Type,
        fields: Collection[ObjectField],
        merged_types: Mapping[str, Thunk[graphql.GraphQLType]] = None,
    ) -> Thunk[graphql.GraphQLType]:
        name, description = self._ref_and_desc
        name = name if name.endswith("Input") else name + "Input"
        visited_fields = dict(map(self._field, fields))
        return lambda: graphql.GraphQLInputObjectType(
            name,
            lambda: merge_fields(cls, visited_fields, merged_types or {}),
            description,
        )

    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool
    ) -> Thunk[graphql.GraphQLType]:
        return self.object(
            cls, [ObjectField(name, type) for name, type in keys.items()]
        )

    def _union_result(
        self, results: Iterable[Thunk[graphql.GraphQLType]]
    ) -> Thunk[graphql.GraphQLType]:
        results = list(results)  # Execute the iteration
        if len(results) == 1:
            return results[0]
        raise TypeError("Union are not supported for input")


class OutputSchemaBuilder(
    SerializationVisitor[Thunk[graphql.GraphQLType]], SchemaBuilder[Serialization]
):
    def __init__(
        self,
        aliaser: Optional[Aliaser],
        is_id: Optional[IdPredicate],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__(aliaser, is_id, union_ref_factory)
        self.input_builder = InputSchemaBuilder(aliaser, is_id, union_ref_factory)

    def _field(self, field: ObjectField) -> Tuple[str, Lazy[graphql.GraphQLField]]:
        if field.resolve is not None:
            resolve = field.resolve
        else:
            resolve = lambda obj, _: getattr(obj, field.name)  # noqa: E731
        field_type = self.visit_with_conversions(field.type, field.conversions)
        args = None
        if field.parameters is not None:
            parameters, types = field.parameters
            args = {}
            for param in parameters:
                default: Any = graphql.Undefined
                param_type = types[param.name]
                # None because of https://github.com/python/typing/issues/775
                if param.default in {None, Undefined, graphql.Undefined}:
                    param_type = Optional[param_type]
                if param.default != Parameter.empty:
                    try:
                        default = serialize(param.default)
                    except Exception:
                        param_type = Optional[param_type]

                def arg_thunk(
                    arg_thunk=self.input_builder.visit(param_type),
                    default=default,
                    out_name=param.name,
                ) -> graphql.GraphQLArgument:
                    arg_type = exec_thunk(arg_thunk)
                    if (
                        not isinstance(arg_type, graphql.GraphQLNonNull)
                        and default is None
                    ):
                        default = graphql.Undefined
                    return graphql.GraphQLArgument(arg_type, default, out_name=out_name)

                args[self.aliaser(param.name)] = arg_thunk
        return self.aliaser(field.alias or field.name), lambda: graphql.GraphQLField(
            exec_thunk(field_type),
            {name: arg() for name, arg in args.items()} if args else None,
            resolve,
            field.subscribe,
            field.description,
            field.deprecated,
        )

    def object(
        self,
        cls: Type,
        fields: Collection[ObjectField],
        merged_types: Mapping[str, Thunk[graphql.GraphQLType]] = None,
    ) -> Thunk[graphql.GraphQLType]:
        fields_and_resolvers = list(fields)
        try:
            name, description = self._ref_and_desc
        except MissingRef:
            if cls.__name__ not in ("Query", "Mutation", "Subscription"):
                raise
            name, description = cls.__name__, self._description
        for resolver_name, resolver in get_resolvers(cls).items():
            resolve = resolver_resolve(resolver, self.aliaser)
            resolver_field = ObjectField(
                resolver_name,
                resolver.return_type,
                conversions=resolver.conversions,
                parameters=(resolver.parameters, resolver.types),
                resolve=resolve,
            )
            fields_and_resolvers.append(resolver_field)
        visited_fields = dict(map(self._field, fields_and_resolvers))

        def field_thunk() -> graphql.GraphQLFieldMap:
            return merge_fields(
                cls,
                visited_fields,
                merged_types or {},
                deref_merged_field,
            )

        interfaces = list(map(self.visit, get_interfaces(cls)))
        interface_thunk = None
        if interfaces:

            def interface_thunk() -> Collection[graphql.GraphQLInterfaceType]:
                result = {exec_thunk(i, non_null=False) for i in interfaces}
                for merged_thunk in (merged_types or {}).values():
                    merged = cast(
                        Union[graphql.GraphQLObjectType, graphql.GraphQLInterfaceType],
                        exec_thunk(merged_thunk, non_null=False),
                    )
                    result.update(merged.interfaces)
                return sorted(result, key=lambda i: i.name)

        if is_interface(cls):
            return lambda: graphql.GraphQLInterfaceType(
                name,
                field_thunk,
                interface_thunk,
                description=description,
            )

        else:
            return lambda: graphql.GraphQLObjectType(
                name,
                field_thunk,
                interface_thunk,
                is_type_of=lambda obj, _: isinstance(obj, cls),
                description=description,
            )

    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool
    ) -> Thunk[graphql.GraphQLType]:
        raise TypeError("TyedDict are not supported in output schema")

    def _union_result(
        self, results: Iterable[Thunk[graphql.GraphQLType]]
    ) -> Thunk[graphql.GraphQLType]:
        results = list(results)  # Execute the iteration
        if len(results) == 1:
            return results[0]
        name, description = self._ref, self._description
        if name is None and self.union_ref_factory is None:
            raise MissingRef

        def thunk() -> graphql.GraphQLUnionType:
            types = [exec_thunk(res, non_null=False) for res in results]
            if name is None:
                assert self.union_ref_factory is not None
                computed_name = self.union_ref_factory([t.name for t in types])
            else:
                computed_name = name
            return graphql.GraphQLUnionType(
                computed_name, types, description=description
            )

        return thunk


async_iterable_origins = set(map(get_origin, (AsyncIterable[Any], AsyncIterator[Any])))

_fake_type = cast(type, ...)


@dataclass(frozen=True)
class Operation(Generic[T]):
    function: Callable[..., T]
    alias: Optional[str] = None
    conversions: Optional[Conversions] = None
    schema: Optional[Schema] = None
    error_handler: ErrorHandler = Undefined


OpOrFunc = Union[Callable[..., T], Operation[T]]


def operation_resolver(
    operation: OpOrFunc, *, keep_first_param=False
) -> Tuple[str, Resolver]:
    if not isinstance(operation, Operation):
        operation = Operation(operation)
    error_handler: Optional[Callable]
    if operation.error_handler is Undefined:
        error_handler = None
    elif operation.error_handler is None:
        error_handler = none_error_handler
    else:
        error_handler = operation.error_handler
    if keep_first_param:
        wrapper = operation.function
    else:
        op = operation.function
        if iscoroutinefunction(op):

            async def wrapper(_, *args, **kwargs):
                return await op(*args, **kwargs)

        else:

            def wrapper(_, *args, **kwargs):
                return op(*args, **kwargs)

        wrapper.__annotations__ = op.__annotations__

    (*parameters,) = resolver_parameters(
        operation.function, check_first=not keep_first_param
    )
    if keep_first_param:
        parameters = parameters[1:]
    return operation.alias or operation.function.__name__, Resolver(
        wrapper, operation.conversions, operation.schema, error_handler, parameters
    )


def remove_error_handler(subscription: OpOrFunc) -> OpOrFunc:
    if (
        isinstance(subscription, Operation)
        and subscription.error_handler is not Undefined
    ):
        warnings.warn("Subscriber error_handler is ignored")
        return replace(subscription, error_handler=Undefined)
    else:
        return subscription


def graphql_schema(
    *,
    query: Iterable[OpOrFunc] = (),
    mutation: Iterable[OpOrFunc] = (),
    subscription: Iterable[
        Union[
            OpOrFunc[AsyncIterable],
            Tuple[Callable[..., AsyncIterable], OpOrFunc],
        ]
    ] = (),
    types: Iterable[Type] = (),
    directives: Optional[Collection[graphql.GraphQLDirective]] = None,
    description: Optional[str] = None,
    extensions: Optional[Dict[str, Any]] = None,
    aliaser: Aliaser = to_camel_case,
    id_types: Union[Collection[AnyType], IdPredicate] = None,
    union_ref: UnionRefFactory = "Or".join,
) -> graphql.GraphQLSchema:

    query_fields: List[ObjectField] = []
    mutation_fields: List[ObjectField] = []
    subscription_fields: List[ObjectField] = []
    for operations, fields in [(query, query_fields), (mutation, mutation_fields)]:
        for operation in operations:
            name, resolver = operation_resolver(operation)
            fields.append(
                ObjectField(
                    name,
                    resolver.return_type,
                    parameters=(resolver.parameters, resolver.types),
                    resolve=resolver_resolve(resolver, aliaser),
                    schema=resolver.schema,
                )
            )
    for sub_op in subscription:  # type: ignore
        resolve: Callable
        if isinstance(sub_op, tuple):
            operation, event_handler = cast(Tuple[Callable, OpOrFunc], sub_op)
            operation = remove_error_handler(operation)
            name, resolver = operation_resolver(event_handler, keep_first_param=True)
            _, subscriber = operation_resolver(operation)
            subscribe = resolver_resolve(subscriber, aliaser, serialized=False)
            resolve = resolver_resolve(resolver, aliaser)
            return_type = resolver.return_type
        else:
            operation = remove_error_handler(cast(OpOrFunc, sub_op))
            name, resolver = operation_resolver(sub_op)
            if get_origin(resolver.return_type) not in async_iterable_origins:
                raise TypeError(
                    "Subscriptions must return an AsyncIterable/AsyncIterator"
                )
            return_type = get_args(resolver.return_type)[0]
            subscribe = resolver_resolve(resolver, aliaser, serialized=False)

            def resolve(_, *args, **kwargs):
                return _

        subscription_fields.append(
            ObjectField(
                name,
                return_type,
                parameters=(resolver.parameters, resolver.types),
                resolve=resolve,
                subscribe=subscribe,
                schema=resolver.schema,
            )
        )

    is_id = id_types.__contains__ if isinstance(id_types, Collection) else id_types
    builder = OutputSchemaBuilder(aliaser, is_id, union_ref)

    def root_type(
        name: str, fields: Collection[ObjectField]
    ) -> Optional[graphql.GraphQLObjectType]:
        if not fields and name != "Query":
            return None
        return exec_thunk(builder.object(type(name, (), {}), fields), non_null=False)

    return graphql.GraphQLSchema(
        query=root_type("Query", query_fields),
        mutation=root_type("Mutation", mutation_fields),
        subscription=root_type("Subscription", subscription_fields),
        types=[exec_thunk(builder.visit(cls), non_null=False) for cls in types],
        directives=directives,
        description=description,
        extensions=extensions,
    )
