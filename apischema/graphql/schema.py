from contextlib import contextmanager
from dataclasses import InitVar, dataclass, field as field_
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

from apischema.aliases import Aliaser
from apischema.conversions import identity
from apischema.conversions.conversions import Conversions, to_hashable_conversions
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dataclasses import replace
from apischema.graphql.interfaces import get_interfaces, is_interface
from apischema.graphql.resolvers import (
    Resolver,
    get_resolvers,
    none_error_handler,
    partial_serialization_method,
    resolver_parameters,
    resolver_resolve,
)
from apischema.json_schema.schemas import Schema, get_schema, merge_schema
from apischema.metadata.keys import SCHEMA_METADATA
from apischema.objects import AliasedStr, ObjectField
from apischema.objects.utils import annotated_metadata
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.serialization import serialize
from apischema.serialization.serialized_methods import ErrorHandler
from apischema.type_names import TypeNameFactory, get_type_name
from apischema.types import AnyType, NoneType, OrderedDict, Undefined, UndefinedType
from apischema.typing import get_args, get_origin
from apischema.utils import (
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


class MissingName(Exception):
    pass


class Nullable(Exception):
    pass


T = TypeVar("T")
Lazy = Callable[[], T]
Thunk = Union[Callable[[], T], T]

TypeThunk = Thunk[graphql.GraphQLType]


def exec_thunk(thunk: TypeThunk, *, non_null=None) -> Any:
    result = thunk if isinstance(thunk, graphql.GraphQLType) else thunk()
    if non_null is True and not isinstance(result, graphql.GraphQLNonNull):
        return graphql.GraphQLNonNull(result)  # type: ignore
    if non_null is False and isinstance(result, graphql.GraphQLNonNull):
        return result.of_type
    return result


def merged_schema(
    schema: Optional[Schema], tp: Optional[AnyType]
) -> Tuple[Optional[Schema], Mapping[str, Any]]:
    if tp is not None and get_origin(tp) == Annotated:
        for annotation in reversed(get_args(tp)[1:]):
            if isinstance(annotation, TypeNameFactory):
                break
            elif isinstance(annotation, Mapping) and SCHEMA_METADATA in annotation:
                schema = merge_schema(annotation[SCHEMA_METADATA], schema)
    schema_dict: Dict[str, Any] = {}
    if schema is not None:
        schema.merge_into(schema_dict)
    return schema, schema_dict


def get_description(
    schema: Optional[Schema], tp: Optional[AnyType] = None
) -> Optional[str]:
    _, schema_dict = merged_schema(schema, tp)
    return schema_dict.get("description")


def get_deprecated(
    schema: Optional[Schema], tp: Optional[AnyType] = None
) -> Optional[str]:
    schema, schema_dict = merged_schema(schema, tp)
    if not schema_dict.get("deprecated", False):
        return None
    while schema is not None:
        if schema.annotations is not None:
            if isinstance(schema.annotations.deprecated, str):
                return schema.annotations.deprecated
            elif schema.annotations.deprecated:
                return graphql.DEFAULT_DEPRECATION_REASON
        schema = schema.child
    return graphql.DEFAULT_DEPRECATION_REASON


@dataclass(frozen=True)
class ResolverField:
    to_alias: InitVar[str]
    alias: str = field_(init=False)
    resolver: Resolver
    types: Mapping[str, AnyType]
    parameters: Sequence[Parameter]
    metadata: Mapping[str, Mapping]
    subscribe: Optional[Callable] = None

    def __post_init__(self, to_alias: str):
        object.__setattr__(self, "alias", AliasedStr(to_alias))

    @property
    def name(self) -> str:
        return self.resolver.func.__name__

    @property
    def type(self) -> AnyType:
        return self.types["return"]

    @property
    def description(self) -> Optional[str]:
        return get_description(self.resolver.schema)

    @property
    def deprecated(self) -> Optional[str]:
        return get_deprecated(self.resolver.schema)


IdPredicate = Callable[[AnyType], bool]
UnionNameFactory = Callable[[Sequence[str]], str]


def annotated_schema(tp: AnyType) -> Optional[Schema]:
    schema = None
    if get_origin(tp) == Annotated:
        for annotation in get_args(tp)[1:]:
            if isinstance(annotation, Mapping) and SCHEMA_METADATA in annotation:
                schema = merge_schema(annotation[SCHEMA_METADATA], schema)
    return schema


class SchemaBuilder(ConversionsVisitor[Conv, TypeThunk], ObjectVisitor[TypeThunk]):
    def __init__(
        self,
        aliaser: Aliaser,
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
        union_name_factory: Optional[UnionNameFactory],
    ):
        super().__init__()

        def _aliaser(s: str) -> str:
            return aliaser(s) if isinstance(s, AliasedStr) else s

        self.aliaser = _aliaser
        self.id_type = id_type
        self.is_id = is_id or (lambda t: False)
        self.union_name_factory = union_name_factory
        self._cache: Dict[Any, TypeThunk] = {}
        self._non_null = True
        self._name: Optional[str] = None
        self._schema: Optional[Schema] = None
        self._merge_next: bool = False

    @property
    def _description(self) -> Optional[str]:
        return get_description(self._schema)

    @property
    def _name_and_desc(self) -> Tuple[str, Optional[str]]:
        if self._name is None:
            raise MissingName
        return self._name, self._description

    @contextmanager
    def _replace_name_and_schema(
        self, ref: Optional[str], schema: Optional[Schema], merge_next: bool
    ):
        name_save, schema_save, merge_save = self._name, self._schema, self._merge_next
        self._name, self._schema, self._merge_next = ref, schema, merge_next
        try:
            yield
        finally:
            self._name, self._schema, self._merge_next = (
                name_save,
                schema_save,
                merge_save,
            )

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> TypeThunk:
        annotated_name, annotated_schema = self._name, self._schema
        for annotation in reversed(annotations):
            if isinstance(annotation, TypeNameFactory):
                annotated_name = annotated_name or annotation.to_type_name(tp).graphql
            if isinstance(annotation, Mapping) and SCHEMA_METADATA in annotation:
                if annotated_name is not None:
                    annotated_schema = merge_schema(
                        annotation[SCHEMA_METADATA], annotated_schema
                    )
        with self._replace_name_and_schema(annotated_name, annotated_schema, True):
            return self.visit(tp)

    def any(self) -> TypeThunk:
        return JsonScalar

    def collection(self, cls: Type[Collection], value_type: AnyType) -> TypeThunk:
        value_thunk = self.visit(value_type)
        return lambda: graphql.GraphQLList(exec_thunk(value_thunk))

    def _visit_merged(self, field: ObjectField) -> TypeThunk:
        raise NotImplementedError

    def enum(self, cls: Type[Enum]) -> TypeThunk:
        return self.literal([elt.value for elt in cls])

    def literal(self, values: Sequence[Any]) -> TypeThunk:
        if not all(isinstance(v, str) for v in values):
            raise TypeError("apischema GraphQL only support Enum/Literal of strings")
        name, description = self._name_and_desc
        return graphql.GraphQLEnumType(
            name, dict(zip(values, values)), description=description
        )

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> TypeThunk:
        try:
            name, description = self._name_and_desc
            return graphql.GraphQLScalarType(name, description=description)
        except MissingName:
            return JsonScalar

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> TypeThunk:
        raise NotImplementedError

    def primitive(self, cls: Type) -> TypeThunk:
        assert cls is not NoneType
        try:
            name, description = self._name_and_desc
            return graphql.GraphQLScalarType(name, description=description)
        except MissingName:
            return GRAPHQL_PRIMITIVE_TYPES[cls]

    def tuple(self, types: Sequence[AnyType]) -> TypeThunk:
        raise TypeError("Tuple are not supported")

    def _use_cache(self, key: Any, thunk: Lazy[TypeThunk]) -> TypeThunk:
        full_key = key, self._name, self._schema, self._conversions
        if full_key not in self._cache:
            cache = None

            def rec_sentinel() -> graphql.GraphQLType:
                nonlocal cache
                assert cache is not None
                if not isinstance(cache, graphql.GraphQLType):
                    cache = exec_thunk(cache)
                return cache

            self._cache[full_key] = rec_sentinel
            cache = thunk()

        return self._cache[full_key]

    def union(self, alternatives: Sequence[AnyType]) -> TypeThunk:
        if UndefinedType in alternatives:
            filtered = [alt for alt in alternatives if alt is not UndefinedType]
            alternatives = [*filtered, NoneType]
        results = []
        non_null_alternatives = []
        for alt in alternatives:
            try:
                results.append(self.visit(alt))
                non_null_alternatives.append(alt)
            except Nullable:
                self._non_null = False
        if not results:
            raise TypeError("Empty union")
        if len(results) == 1:
            return results[0]
        return self._use_cache(
            tuple(non_null_alternatives), lambda: self._union_result(results)
        )

    def visit_conversion(
        self, tp: AnyType, conversion: Optional[Conv], dynamic: bool
    ) -> TypeThunk:
        if dynamic:
            with self._replace_name_and_schema(None, None, False):
                return super().visit_conversion(tp, conversion, dynamic)
        if self.is_id(tp) or tp == ID:
            return graphql.GraphQLNonNull(self.id_type)
        name, schema = get_type_name(tp).graphql, get_schema(tp)
        if self._merge_next:
            name, schema = self._name or name, merge_schema(schema, self._schema)
        if get_origin(tp) == Annotated or hasattr(tp, "__supertype__"):
            with self._replace_name_and_schema(name, schema, True):
                return super().visit_conversion(tp, conversion, dynamic)
        if get_args(tp):
            schema = merge_schema(get_schema(get_origin(tp)), schema)
        non_null_save = self._non_null
        self._non_null = True
        try:
            with self._replace_name_and_schema(name, schema, conversion is not None):
                result = super().visit_conversion(tp, conversion, dynamic)
            non_null = self._non_null
            return lambda: exec_thunk(result, non_null=non_null)
        except MissingName:
            raise TypeError(f"Missing ref for type {tp}") from None
        finally:
            self._non_null = non_null_save

    def _visit_not_generic(self, tp: AnyType) -> TypeThunk:
        if tp is NoneType:
            raise Nullable
        _visit = super()._visit_not_generic
        return self._use_cache(self._generic or tp, lambda: _visit(tp))


FieldType = TypeVar("FieldType", graphql.GraphQLInputField, graphql.GraphQLField)


def merge_fields(
    cls: Type,
    fields: Mapping[str, Lazy[FieldType]],
    merged_types: Mapping[str, TypeThunk],
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
    SchemaBuilder[Deserialization],
    DeserializationVisitor[TypeThunk],
    DeserializationObjectVisitor[TypeThunk],
):
    def _visit_merged(self, field: ObjectField) -> TypeThunk:
        with self._replace_conversions(field.deserialization):
            return self.visit(field.type)

    def _field(self, field: ObjectField) -> Lazy[graphql.GraphQLInputField]:
        field_type = field.type
        field_default = graphql.Undefined if field.required else field.get_default()
        default: Any = graphql.Undefined
        # Don't put `null` default + handle Undefined as None
        if field_default in {None, Undefined}:
            field_type = Optional[field_type]
        elif field_default is not graphql.Undefined:
            try:
                default = serialize(
                    field_default,
                    conversions=field.deserialization,
                    aliaser=self.aliaser,
                )
            except Exception:
                field_type = Optional[field_type]

        with self._replace_conversions(field.deserialization):
            type_thunk = self.visit(field_type)

        return lambda: graphql.GraphQLInputField(
            exec_thunk(type_thunk),
            default_value=default,
            description=get_description(field.schema, field.type),
        )

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> TypeThunk:
        name, description = self._name_and_desc
        name = name if name.endswith("Input") else name + "Input"
        visited_fields = {
            self.aliaser(f.alias): self._field(f) for f in fields if not f.is_aggregate
        }
        merged_types = {f.name: self._visit_merged(f) for f in fields if f.merged}
        return lambda: graphql.GraphQLInputObjectType(
            name, lambda: merge_fields(cls, visited_fields, merged_types), description
        )

    def _union_result(self, results: Iterable[TypeThunk]) -> TypeThunk:
        results = list(results)
        # Check must be done here too because _union_result is used by visit_conversion
        if len(results) == 1:
            return results[0]
        else:
            raise TypeError("Union are not supported for input")


class OutputSchemaBuilder(
    SchemaBuilder[Serialization],
    SerializationVisitor[TypeThunk],
    SerializationObjectVisitor[TypeThunk],
):
    def __init__(
        self,
        aliaser: Aliaser,
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
        union_name_factory: Optional[UnionNameFactory],
    ):
        super().__init__(aliaser, id_type, is_id, union_name_factory)
        self.input_builder = InputSchemaBuilder(
            aliaser, id_type, is_id, union_name_factory
        )
        self._get_merged: Optional[Callable[[Any], Any]] = None

    def _wrap_resolve(self, resolve: Callable):
        if self._get_merged is None:
            return resolve
        else:
            get_merged = self._get_merged

            def resolve_wrapper(__obj, __info, **kwargs):
                return resolve(get_merged(__obj), __info, **kwargs)

            return resolve_wrapper

    def _field(self, field: ObjectField) -> Lazy[graphql.GraphQLField]:
        field_name, aliaser = field.name, self.aliaser
        conversions = to_hashable_conversions(field.serialization)

        @self._wrap_resolve
        def resolve(obj, _):
            attr = getattr(obj, field_name)
            return partial_serialization_method(attr.__class__, conversions, aliaser)(
                attr, False
            )

        with self._replace_conversions(conversions):
            type_thunk = self.visit(field.type)
        return lambda: graphql.GraphQLField(
            exec_thunk(type_thunk),
            None,
            resolve,
            description=get_description(field.schema, field.type),
            deprecation_reason=get_deprecated(field.schema, field.type),
        )

    def _resolver(self, field: ResolverField) -> Lazy[graphql.GraphQLField]:
        resolve = self._wrap_resolve(
            resolver_resolve(field.resolver, field.types, self.aliaser)
        )
        with self._replace_conversions(field.resolver.conversions):
            type_thunk = self.visit(field.type)
        args = None
        if field.parameters is not None:
            args = {}
            for param in field.parameters:
                default: Any = graphql.Undefined
                param_type = field.types[param.name]
                if is_union_of(param_type, graphql.GraphQLResolveInfo):
                    break
                metadata = annotated_metadata(param_type)
                if param.name in field.metadata:
                    metadata = {**metadata, **field.metadata[param.name]}
                param_field = ObjectField(
                    param.name,
                    param_type,
                    param.default is Parameter.empty,
                    metadata,
                    default=param.default,
                )
                if param_field.required:
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
                with self._replace_conversions(param_field.deserialization):
                    arg_type = self.input_builder.visit(param_type)
                description = get_description(
                    merge_schema(
                        metadata.get(SCHEMA_METADATA),
                        field.metadata.get(param.name, {}).get(SCHEMA_METADATA),
                    ),
                    param_type,
                )

                def arg_thunk(
                    arg_type=arg_type, default=default, description=description
                ) -> graphql.GraphQLArgument:
                    return graphql.GraphQLArgument(
                        exec_thunk(arg_type), default, description
                    )

                args[self.aliaser(param_field.alias)] = arg_thunk
        return lambda: graphql.GraphQLField(
            exec_thunk(type_thunk),
            {name: arg() for name, arg in args.items()} if args else None,
            resolve,
            field.subscribe,
            field.description,
            field.deprecated,
        )

    def _visit_merged(self, field: ObjectField) -> TypeThunk:
        conversions = to_hashable_conversions(field.serialization)
        field_name, aliaser = field.name, self.aliaser
        get_prev_merged = self._get_merged if self._get_merged is not None else identity

        def get_merge(obj):
            attr = getattr(get_prev_merged(obj), field_name)
            return partial_serialization_method(attr.__class__, conversions, aliaser)(
                attr, False
            )

        merged_save = self._get_merged
        self._get_merged = get_merge
        try:
            with self._replace_conversions(conversions):
                return self.visit(field.type)
        finally:
            self._get_merged = merged_save

    def object(
        self,
        cls: Type,
        fields: Sequence[ObjectField],
        resolvers: Sequence[ResolverField] = (),
    ) -> TypeThunk:
        name, description = self._name_and_desc
        all_fields = {f.alias: self._field(f) for f in fields if not f.is_aggregate}
        name_by_aliases = {f.alias: f.name for f in fields}
        all_fields.update({r.alias: self._resolver(r) for r in resolvers})
        name_by_aliases.update({r.alias: r.resolver.func.__name__ for r in resolvers})
        for alias, (resolver, types) in get_resolvers(self._generic or cls).items():
            resolver_field = ResolverField(
                alias,
                resolver,
                types,
                resolver.parameters,
                resolver.parameters_metadata,
            )
            all_fields[alias] = self._resolver(resolver_field)
            name_by_aliases[alias] = resolver.func.__name__
        sorted_fields = sort_by_annotations_position(
            cls, all_fields, name_by_aliases.__getitem__
        )
        visited_fields = OrderedDict(
            (self.aliaser(a), all_fields[a]) for a in sorted_fields
        )
        merged_types = {f.name: self._visit_merged(f) for f in fields if f.merged}

        def field_thunk() -> graphql.GraphQLFieldMap:
            return merge_fields(cls, visited_fields, merged_types)

        interfaces = list(map(self.visit, get_interfaces(cls)))
        interface_thunk = None
        if interfaces:

            def interface_thunk() -> Collection[graphql.GraphQLInterfaceType]:
                result = {exec_thunk(i, non_null=False) for i in interfaces}
                for merged_thunk in (merged_types).values():
                    merged = cast(
                        Union[graphql.GraphQLObjectType, graphql.GraphQLInterfaceType],
                        exec_thunk(merged_thunk, non_null=False),
                    )
                    result.update(merged.interfaces)
                return sorted(result, key=lambda i: i.name)

        if is_interface(cls):
            return lambda: graphql.GraphQLInterfaceType(
                name, field_thunk, interface_thunk, description=description
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
        self, cls: Type, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> TypeThunk:
        raise TypeError("TyedDict are not supported in output schema")

    def _union_result(self, results: Iterable[TypeThunk]) -> TypeThunk:
        results = list(results)  # Execute the iteration (tuple to be hashable)
        name, description = self._name, self._description
        if name is None and self.union_name_factory is None:
            raise MissingName

        def thunk() -> graphql.GraphQLUnionType:
            # No need to use a thunk here because union can only have class members,
            # which use already thunks.
            types = [exec_thunk(res, non_null=False) for res in results]
            if name is None:
                assert self.union_name_factory is not None
                computed_name = self.union_name_factory([t.name for t in types])
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
    # TODO deprecate union_ref parameter
    union_ref: UnionNameFactory = "Or".join,
    union_name: UnionNameFactory = "Or".join,
) -> graphql.GraphQLSchema:

    query_fields: List[ResolverField] = []
    mutation_fields: List[ResolverField] = []
    subscription_fields: List[ResolverField] = []
    for operations, op_class, fields in [
        (query, Query, query_fields),
        (mutation, Mutation, mutation_fields),
    ]:
        for operation in operations:  # type: ignore
            alias, resolver = operation_resolver(operation, op_class)
            resolver_field = ResolverField(
                alias,
                resolver,
                resolver.types(),
                resolver.parameters,
                resolver.parameters_metadata,
            )
            fields.append(resolver_field)
    for sub_op in subscription:  # type: ignore
        if not isinstance(sub_op, Subscription):
            sub_op = Subscription(sub_op)  # type: ignore
        sub_parameters: Sequence[Parameter]
        if sub_op.resolver is not None:
            alias = sub_op.alias or sub_op.resolver.__name__
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
            subscriber = replace(subscriber2, error_handler=None)
            subscribe = resolver_resolve(
                subscriber, subscriber.types(), aliaser, serialized=False
            )
        else:
            alias, subscriber2 = operation_resolver(sub_op, Subscription)
            resolver = Resolver(
                lambda _: _,
                sub_op.conversions,
                sub_op.schema,
                subscriber2.error_handler,
                (),
                {},
            )
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
            sub_types = {**sub_types, "return": resolver.return_type(event_type)}

        resolver_field = ResolverField(
            alias,
            resolver,
            sub_types,
            sub_parameters,
            sub_op.parameters_metadata,
            subscribe,
        )
        subscription_fields.append(resolver_field)

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
    builder = OutputSchemaBuilder(aliaser, id_type, is_id, union_name or union_ref)

    def root_type(
        name: str, fields: Sequence[ResolverField]
    ) -> Optional[graphql.GraphQLObjectType]:
        if not fields:
            return None
        with builder._replace_name_and_schema(name, None, False):
            return exec_thunk(
                builder.object(type(name, (), {}), (), fields), non_null=False
            )

    return graphql.GraphQLSchema(
        query=root_type("Query", query_fields),
        mutation=root_type("Mutation", mutation_fields),
        subscription=root_type("Subscription", subscription_fields),
        types=[exec_thunk(builder.visit(cls), non_null=False) for cls in types],
        directives=directives,
        description=description,
        extensions=extensions,
    )
