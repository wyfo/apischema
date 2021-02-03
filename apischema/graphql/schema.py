from dataclasses import Field, InitVar, dataclass, field as field_
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
    NewType,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import graphql

from apischema import UndefinedType, serialize
from apischema.aliases import Aliaser
from apischema.conversions import identity
from apischema.conversions.conversions import Conversions
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dataclass_utils import (
    get_alias,
    get_default,
    get_field_conversions,
    get_fields,
    is_required,
)
from apischema.dataclasses import replace
from apischema.graphql.interfaces import get_interfaces, is_interface
from apischema.graphql.resolvers import (
    Resolver,
    get_resolvers,
    none_error_handler,
    partial_serialize,
    resolver_parameters,
    resolver_resolve,
)
from apischema.json_schema.refs import get_ref, schema_ref
from apischema.json_schema.schema import Schema, get_schema, merge_schema
from apischema.metadata.implem import ConversionMetadata
from apischema.metadata.keys import (
    CONVERSIONS_METADATA,
    MERGED_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SCHEMA_METADATA,
    check_metadata,
    get_annotated_metadata,
)
from apischema.serialization.serialized_methods import ErrorHandler
from apischema.skip import filter_skipped
from apischema.types import AnyType, NoneType
from apischema.typing import get_args, get_origin
from apischema.utils import (
    Undefined,
    get_args2,
    get_origin2,
    is_union_of,
    sort_by_annotations_position,
    to_camel_case,
)

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

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

ID = NewType("ID", str)


class MissingRef(Exception):
    pass


class Nullable(Exception):
    pass


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
    parameters: Optional[
        Tuple[Collection[Parameter], Mapping[str, AnyType], Mapping[str, Mapping]]
    ] = None
    resolve: Optional[Callable] = None
    schema: InitVar[Optional[Schema]] = None
    subscribe: Optional[Callable] = None
    deprecated: Optional[str] = field_(init=False, default=None)
    description: Optional[str] = field_(init=False, default=None)

    def __post_init__(self, schema: Optional[Schema]):
        if schema is not None and schema.annotations is not None:
            object.__setattr__(self, "description", schema.annotations.description)
            if schema.annotations.deprecated is True:
                object.__setattr__(
                    self, "deprecated", graphql.DEFAULT_DEPRECATION_REASON
                )
            elif isinstance(schema.annotations.deprecated, str):
                object.__setattr__(self, "deprecated", schema.annotations.deprecated)
            if schema.annotations.default is not Undefined:
                object.__setattr__(self, "default", schema.annotations.default)


IdPredicate = Callable[[AnyType], bool]
UnionRefFactory = Callable[[Sequence[str]], str]


def annotated_schema(tp: AnyType) -> Optional[Schema]:
    schema = None
    if get_origin(tp) == Annotated:
        for annotation in get_args(tp)[1:]:
            if isinstance(annotation, Mapping) and SCHEMA_METADATA in annotation:
                schema = merge_schema(annotation[SCHEMA_METADATA], schema)
    return schema


class SchemaBuilder(ConversionsVisitor[Conv, Thunk[graphql.GraphQLType]]):
    def __init__(
        self,
        aliaser: Optional[Aliaser],
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__()
        self.aliaser = aliaser or (lambda s: s)
        self.id_type = id_type
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
        self, tp: AnyType, annotations: Sequence[Any]
    ) -> Thunk[graphql.GraphQLType]:
        for annotation in annotations:
            if isinstance(annotation, schema_ref):
                annotation.check_type(tp)
                ref = annotation.ref
                if not isinstance(ref, str):
                    raise ValueError("Annotated schema_ref can only be str")
                self._ref = self._ref or ref
            if isinstance(annotation, Mapping) and SCHEMA_METADATA in annotation:
                self._schema = merge_schema(annotation[SCHEMA_METADATA], self._schema)
        return self.visit_with_schema(tp, self._ref, self._schema)

    def any(self) -> Thunk[graphql.GraphQLType]:
        return JsonScalar

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Thunk[graphql.GraphQLType]:
        value_thunk = self.visit(value_type)
        return lambda: graphql.GraphQLList(exec_thunk(value_thunk))

    def _object_field(self, field: Field, field_type: AnyType) -> ObjectField:
        return ObjectField(
            field.name,
            field_type,
            alias=get_alias(field),
            conversions=get_field_conversions(field, self.operation),
            default=graphql.Undefined if is_required(field) else get_default(field),
            schema=merge_schema(
                annotated_schema(field_type), field.metadata.get(SCHEMA_METADATA)
            ),
        )

    def _visit_merged(
        self, field: Field, field_type: AnyType
    ) -> Thunk[graphql.GraphQLType]:
        return self.visit_with_conversions(
            field_type, get_field_conversions(field, self.operation)
        )

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Thunk[graphql.GraphQLType]:
        object_fields: List[ObjectField] = []
        merged_types: Dict[str, Thunk[graphql.GraphQLType]] = {}
        for field in get_fields(fields, init_vars, self.operation):
            check_metadata(field)
            if MERGED_METADATA in field.metadata:
                merged_types[field.name] = self._visit_merged(field, types[field.name])
            elif PROPERTIES_METADATA in field.metadata:
                continue
            else:
                object_fields.append(self._object_field(field, types[field.name]))
        return self.object(cls, object_fields, merged_types)

    def enum(self, cls: Type[Enum]) -> Thunk[graphql.GraphQLType]:
        return self.literal([elt.value for elt in cls])

    def generic(self, tp: AnyType) -> Thunk[graphql.GraphQLType]:
        self._ref = self._ref or get_ref(tp)
        return super().generic(tp)

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
        fields = [
            ObjectField(
                field_name,
                field_type,
                default=defaults.get(field_name, graphql.Undefined),
                schema=annotated_schema(field_type),
            )
            for field_name, field_type in types.items()
        ]
        return self.object(cls, fields)

    def new_type(self, tp: Type, super_type: AnyType) -> Thunk[graphql.GraphQLType]:
        return self.visit_with_schema(super_type, self._ref, self._schema)

    def object(
        self,
        cls: Type,
        fields: Collection[ObjectField],
        merged_types: Mapping[str, Thunk[graphql.GraphQLType]] = None,
    ) -> Thunk[graphql.GraphQLType]:
        raise NotImplementedError

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
        self, tp: AnyType, ref: Optional[str], schema: Optional[Schema]
    ) -> Thunk[graphql.GraphQLType]:
        if self.is_id(tp) or tp == ID:
            return graphql.GraphQLNonNull(self.id_type)
        if self._apply_dynamic_conversions(tp) is None:
            ref, schema = ref or get_ref(tp), merge_schema(get_schema(tp), schema)
        else:
            ref, schema = None, None
        ref_save, schema_save, non_null_save = self._ref, self._schema, self._non_null
        self._ref, self._schema, self._non_null = ref, schema, True
        try:
            result = super().visit(tp)
            non_null = self._non_null
            return lambda: exec_thunk(result, non_null=non_null)
        except MissingRef:
            raise TypeError(f"Missing ref for type {tp}") from None
        finally:
            self._ref, self._schema = ref_save, schema_save
            self._non_null = non_null_save

    def _visit(self, tp: AnyType) -> Thunk[graphql.GraphQLType]:
        key = self._generic or tp, self._ref, self._schema, self._conversions
        if key in self._cache:
            return self._cache[key]
        cache = None

        def rec_sentinel() -> graphql.GraphQLType:
            assert cache is not None
            return cache

        self._cache[key] = rec_sentinel
        try:
            cache = exec_thunk(super()._visit(tp))
        except Exception:
            del self._cache[key]
            raise
        else:
            return cache

    def visit(self, tp: AnyType) -> Thunk[graphql.GraphQLType]:
        return self.visit_with_schema(tp, None, None)


FieldType = TypeVar("FieldType", graphql.GraphQLInputField, graphql.GraphQLField)


def merge_fields(
    cls: Type,
    fields: Mapping[str, Lazy[FieldType]],
    merged_types: Mapping[str, Thunk[graphql.GraphQLType]],
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
        all_merged_fields.update(merged_fields)
    return {**{name: field() for name, field in fields.items()}, **all_merged_fields}


class InputSchemaBuilder(
    DeserializationVisitor[Thunk[graphql.GraphQLType]],
    SchemaBuilder[Deserialization],
):
    def _field(self, field: ObjectField) -> Tuple[str, Lazy[graphql.GraphQLInputField]]:
        field_type = field.type
        default: Any = graphql.Undefined
        # Don't put `null` default + handle Undefined as None
        if field.default in {None, Undefined}:
            field_type = Optional[field_type]
        elif field.default is not graphql.Undefined:
            try:
                default = serialize(
                    field.default, conversions=field.conversions, aliaser=self.aliaser
                )
            except Exception:
                field_type = Optional[field_type]

        type_thunk = self.visit_with_conversions(field_type, field.conversions)

        def field_thunk():
            return graphql.GraphQLInputField(
                exec_thunk(type_thunk),
                default_value=default,
                description=field.description,
            )

        return self.aliaser(field.alias or field.name), field_thunk

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
        fields = [
            ObjectField(name, type, schema=annotated_schema(type))
            for name, type in keys.items()
        ]
        return self.object(cls, fields)

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
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__(aliaser, id_type, is_id, union_ref_factory)
        self.input_builder = InputSchemaBuilder(
            aliaser, id_type, is_id, union_ref_factory
        )
        self._get_merged: Optional[Callable] = None

    def _wrap_resolve(self, resolve: Callable):
        if self._get_merged is None:
            return resolve
        else:
            get_merged = self._get_merged

            def resolve_wrapper(__obj, __info, **kwargs):
                return resolve(get_merged(__obj), __info, **kwargs)

            return resolve_wrapper

    def _field(self, field: ObjectField) -> Tuple[str, Lazy[graphql.GraphQLField]]:
        if field.resolve is not None:
            resolve = field.resolve
        else:
            field_name, aliaser = field.name, self.aliaser
            conversions = field.conversions

            def resolve(obj, _):
                return partial_serialize(
                    getattr(obj, field_name), aliaser=aliaser, conversions=conversions
                )

        resolve = self._wrap_resolve(resolve)

        field_type = field.type
        if is_union_of(field_type, UndefinedType):
            field_type = Optional[field_type]
        type_thunk = self.visit_with_conversions(field_type, field.conversions)
        args = None
        if field.parameters is not None:
            parameters, types, params_metadata = field.parameters
            args = {}
            for param in parameters:
                default: Any = graphql.Undefined
                param_type = types[param.name]
                if is_union_of(param_type, graphql.GraphQLResolveInfo):
                    break
                metadata = get_annotated_metadata(param_type)
                if param.name in params_metadata:
                    metadata = {**metadata, **params_metadata[param.name]}
                if REQUIRED_METADATA in metadata:
                    pass
                # Don't put `null` default + handle Undefined as None
                # also https://github.com/python/typing/issues/775
                elif param.default in {None, Undefined}:
                    param_type = Optional[param_type]
                # param.default == graphql.Undefined means the parameter is required
                # even if it has a default
                elif param.default not in {Parameter.empty, graphql.Undefined}:
                    try:
                        default = serialize(param.default)
                    except Exception:
                        param_type = Optional[param_type]
                conversions = metadata.get(
                    CONVERSIONS_METADATA, ConversionMetadata()
                ).deserialization
                arg_type = self.input_builder.visit_with_conversions(
                    param_type, conversions
                )
                description = None
                if SCHEMA_METADATA in metadata:
                    schema: Schema = metadata[SCHEMA_METADATA]
                    if schema.annotations is not None:
                        description = schema.annotations.description

                def arg_thunk(
                    arg_type=arg_type, default=default, description=description
                ) -> graphql.GraphQLArgument:
                    return graphql.GraphQLArgument(
                        exec_thunk(arg_type), default, description
                    )

                args[self.aliaser(param.name)] = arg_thunk
        return self.aliaser(field.alias or field.name), lambda: graphql.GraphQLField(
            exec_thunk(type_thunk),
            {name: arg() for name, arg in args.items()} if args else None,
            resolve,
            field.subscribe,
            field.description,
            field.deprecated,
        )

    def _visit_merged(
        self, field: Field, field_type: AnyType
    ) -> Thunk[graphql.GraphQLType]:
        conversions = get_field_conversions(field, self.operation)
        field_name, aliaser = field.name, self.aliaser
        get_prev_merged = self._get_merged if self._get_merged is not None else identity

        def get_merge(obj):
            return partial_serialize(
                getattr(get_prev_merged(obj), field_name),
                aliaser=aliaser,
                conversions=conversions,
            )

        merged_save = self._get_merged
        self._get_merged = get_merge
        try:
            return self.visit_with_conversions(field_type, conversions)
        finally:
            self._get_merged = merged_save

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
        for resolver_alias, (resolver, types) in get_resolvers(
            self._generic or cls
        ).items():
            resolver_field = ObjectField(
                resolver.func.__name__,
                types["return"],
                alias=resolver_alias,
                conversions=resolver.conversions,
                parameters=(resolver.parameters, types, resolver.parameters_metadata),
                resolve=self._wrap_resolve(
                    resolver_resolve(resolver, types, self.aliaser)
                ),
            )
            fields_and_resolvers.append(resolver_field)
        fields_and_resolvers = sort_by_annotations_position(
            cls, fields_and_resolvers, lambda f: f.name
        )
        visited_fields = dict(map(self._field, fields_and_resolvers))

        def field_thunk() -> graphql.GraphQLFieldMap:
            return merge_fields(
                cls,
                visited_fields,
                merged_types or {},
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
    parameters_metadata: Mapping[str, Mapping] = field_(default_factory=dict)


class Query(Operation):
    pass


class Mutation(Operation):
    pass


@dataclass(frozen=True)
class Subscription(Operation[AsyncIterable]):
    resolver: Optional[Callable] = None


Op = TypeVar("Op", bound=Operation)


def operation_resolver(
    operation: Union[Callable, Op], op_class: Type[Op]
) -> Tuple[str, Resolver]:
    if not isinstance(operation, op_class):
        operation = op_class(operation)  # type: ignore
    error_handler: Optional[Callable]
    if operation.error_handler is Undefined:
        error_handler = None
    elif operation.error_handler is None:
        error_handler = none_error_handler
    else:
        error_handler = operation.error_handler
    op = operation.function
    if iscoroutinefunction(op):

        async def wrapper(_, *args, **kwargs):
            return await op(*args, **kwargs)

    else:

        def wrapper(_, *args, **kwargs):
            return op(*args, **kwargs)

    wrapper.__annotations__ = op.__annotations__

    (*parameters,) = resolver_parameters(operation.function, check_first=True)
    return operation.alias or operation.function.__name__, Resolver(
        wrapper,
        operation.conversions,
        operation.schema,
        error_handler,
        parameters,
        operation.parameters_metadata,
    )


def graphql_schema(
    *,
    query: Iterable[Union[Callable, Query]] = (),
    mutation: Iterable[Union[Callable, Mutation]] = (),
    subscription: Iterable[Union[Callable[..., AsyncIterable], Subscription]] = (),
    types: Iterable[Type] = (),
    directives: Optional[Collection[graphql.GraphQLDirective]] = None,
    description: Optional[str] = None,
    extensions: Optional[Dict[str, Any]] = None,
    aliaser: Aliaser = to_camel_case,
    id_types: Union[Collection[AnyType], IdPredicate] = None,
    id_encoding: Tuple[
        Optional[Callable[[str], Any]], Optional[Callable[[Any], str]]
    ] = (None, None),
    union_ref: UnionRefFactory = "Or".join,
) -> graphql.GraphQLSchema:

    query_fields: List[ObjectField] = []
    mutation_fields: List[ObjectField] = []
    subscription_fields: List[ObjectField] = []
    for operations, op_class, fields in [
        (query, Query, query_fields),
        (mutation, Mutation, mutation_fields),
    ]:
        for operation in operations:  # type: ignore
            name, resolver = operation_resolver(operation, op_class)
            resolver_types = resolver.types()
            fields.append(
                ObjectField(
                    name,
                    resolver_types["return"],
                    conversions=resolver.conversions,
                    parameters=(
                        resolver.parameters,
                        resolver_types,
                        resolver.parameters_metadata,
                    ),
                    resolve=resolver_resolve(resolver, resolver_types, aliaser),
                    schema=resolver.schema,
                )
            )
    for sub_op in subscription:  # type: ignore
        if not isinstance(sub_op, Subscription):
            sub_op = Subscription(sub_op)  # type: ignore
        sub_parameters: Sequence[Parameter]
        if sub_op.resolver is not None:
            name = sub_op.alias or sub_op.resolver.__name__
            _, subscriber2 = operation_resolver(sub_op, Subscription)
            _, *sub_parameters = resolver_parameters(sub_op.resolver, check_first=False)
            resolver = Resolver(
                sub_op.resolver,
                sub_op.conversions,
                sub_op.schema,
                subscriber2.error_handler,
                sub_parameters,
                sub_op.parameters_metadata,
            )
            sub_types = resolver.types()
            sub_return = sub_types["return"]
            resolve = resolver_resolve(resolver, sub_types, aliaser)
            subscriber = replace(subscriber2, error_handler=None)
            subscribe = resolver_resolve(
                subscriber, subscriber.types(), aliaser, serialized=False
            )
        else:
            name, subscriber2 = operation_resolver(sub_op, Subscription)
            resolver = Resolver(
                lambda _: _,
                sub_op.conversions,
                sub_op.schema,
                subscriber2.error_handler,
                (),
                {},
            )
            resolve = resolver_resolve(resolver, {}, aliaser)
            subscriber = replace(subscriber2, error_handler=None)
            sub_parameters = subscriber.parameters
            sub_types = subscriber.types()
            if get_origin2(sub_types["return"]) not in async_iterable_origins:
                raise TypeError(
                    "Subscriptions must return an AsyncIterable/AsyncIterator"
                )
            event_type = get_args2(sub_types["return"])[0]
            subscribe = resolver_resolve(
                subscriber, sub_types, aliaser, serialized=False
            )
            sub_return = resolver.return_type(event_type)

        subscription_fields.append(
            ObjectField(
                name,
                sub_return,
                conversions=sub_op.conversions,
                parameters=(sub_parameters, sub_types, sub_op.parameters_metadata),
                resolve=resolve,
                subscribe=subscribe,
                schema=sub_op.schema,
            )
        )

    is_id = id_types.__contains__ if isinstance(id_types, Collection) else id_types
    if id_encoding == (None, None):
        id_type: graphql.GraphQLScalarType = graphql.GraphQLID
    else:
        id_deserializer, id_serializer = id_encoding
        id_type = graphql.GraphQLScalarType(
            name="ID",
            serialize=id_serializer or graphql.GraphQLID.serialize,
            parse_value=id_deserializer or graphql.GraphQLID.parse_value,
            parse_literal=graphql.GraphQLID.parse_literal,
            description=graphql.GraphQLID.description,
        )
    builder = OutputSchemaBuilder(aliaser, id_type, is_id, union_ref)

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
