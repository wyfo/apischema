from dataclasses import dataclass
from dataclasses import field as field_
from dataclasses import replace
from enum import Enum
from functools import wraps
from inspect import Parameter, iscoroutinefunction
from itertools import chain
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

from apischema import settings
from apischema.aliases import Aliaser
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.visitor import (
    Conv,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.graphql.interfaces import get_interfaces, is_interface
from apischema.graphql.resolvers import (
    Resolver,
    get_resolvers,
    none_error_handler,
    partial_serialization_method_factory,
    resolver_parameters,
    resolver_resolve,
)
from apischema.json_schema.schema import get_field_schema, get_method_schema, get_schema
from apischema.metadata.keys import SCHEMA_METADATA
from apischema.objects import ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.ordering import Ordering, sort_by_order
from apischema.recursion import RecursiveConversionsVisitor
from apischema.schemas import Schema, merge_schema
from apischema.serialization import SerializationMethod, serialize
from apischema.serialization.serialized_methods import ErrorHandler
from apischema.type_names import TypeName, TypeNameFactory, get_type_name
from apischema.types import AnyType, NoneType, OrderedDict, Undefined, UndefinedType
from apischema.typing import get_args, get_origin, is_annotated
from apischema.utils import (
    Lazy,
    as_predicate,
    context_setter,
    deprecate_kwargs,
    empty_dict,
    get_args2,
    get_origin2,
    get_origin_or_type,
    identity,
    is_union_of,
    to_camel_case,
)

JSON_SCALAR = graphql.GraphQLScalarType("JSON")
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
Thunk = Union[Callable[[], T], T]

TypeThunk = Thunk[graphql.GraphQLType]


def exec_thunk(thunk: TypeThunk, *, non_null=None) -> Any:
    result = thunk if isinstance(thunk, graphql.GraphQLType) else thunk()
    if non_null is True and not isinstance(result, graphql.GraphQLNonNull):
        return graphql.GraphQLNonNull(result)
    if non_null is False and isinstance(result, graphql.GraphQLNonNull):
        return result.of_type
    return result


def get_parameter_schema(
    func: Callable, parameter: Parameter, field: ObjectField
) -> Optional[Schema]:
    from apischema import settings

    return merge_schema(
        settings.base_schema.parameter(func, parameter, field.alias), field.schema
    )


def merged_schema(
    schema: Optional[Schema], tp: Optional[AnyType]
) -> Tuple[Optional[Schema], Mapping[str, Any]]:
    if is_annotated(tp):
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
    resolver: Resolver
    types: Mapping[str, AnyType]
    parameters: Sequence[Parameter]
    metadata: Mapping[str, Mapping]
    subscribe: Optional[Callable] = None


IdPredicate = Callable[[AnyType], bool]
UnionNameFactory = Callable[[Sequence[str]], str]


GraphQLTp = TypeVar("GraphQLTp", graphql.GraphQLInputType, graphql.GraphQLOutputType)

FactoryFunction = Callable[[Optional[str], Optional[str]], GraphQLTp]


@dataclass(frozen=True)
class TypeFactory(Generic[GraphQLTp]):
    factory: FactoryFunction[GraphQLTp]
    name: Optional[str] = None
    description: Optional[str] = None
    # non_null cannot be a field because it can not be forward to factories called in
    # wrapping factories (e.g. recursive wrapper)

    def merge(
        self, type_name: TypeName = TypeName(), schema: Optional[Schema] = None
    ) -> "TypeFactory[GraphQLTp]":
        if type_name == TypeName() and schema is None:
            return self
        return replace(
            self,
            name=type_name.graphql or self.name,
            description=get_description(schema) or self.description,
        )

    @property
    def type(self) -> GraphQLTp:
        return self.factory(self.name, self.description)  # type: ignore

    @property
    def raw_type(self) -> GraphQLTp:
        tp = self.type
        return tp.of_type if isinstance(tp, graphql.GraphQLNonNull) else tp


def unwrap_name(name: Optional[str], tp: AnyType) -> str:
    if name is None:
        raise TypeError(f"Missing name for {tp}")
    return name


Method = TypeVar("Method", bound=Callable[..., TypeFactory])


def cache_type(method: Method) -> Method:
    @wraps(method)
    def wrapper(self: "SchemaBuilder", *args, **kwargs):
        factory = method(self, *args, **kwargs)

        @wraps(factory.factory)  # type: ignore
        def name_cache(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLNonNull:
            if name is None:
                tp = factory.factory(name, description)  # type: ignore
                return graphql.GraphQLNonNull(tp) if tp is not JSON_SCALAR else tp
            # Method is in cache key because scalar types will have the same method,
            # and then be shared by both visitors, while input/output types will have
            # their own cache entry.
            if (name, method, description) in self._cache_by_name:
                tp, cached_args = self._cache_by_name[(name, method, description)]
                if cached_args == (args, kwargs):
                    return tp
            tp = graphql.GraphQLNonNull(factory.factory(name, description))  # type: ignore
            # Don't put args in cache in order to avoid hashable issue
            self._cache_by_name[(name, method, description)] = (tp, (args, kwargs))
            return tp

        return replace(factory, factory=name_cache)

    return cast(Method, wrapper)


class SchemaBuilder(
    RecursiveConversionsVisitor[Conv, TypeFactory[GraphQLTp]],
    ObjectVisitor[TypeFactory[GraphQLTp]],
):
    types: Tuple[Type[graphql.GraphQLType], ...]

    def __init__(
        self,
        aliaser: Aliaser,
        enum_aliaser: Aliaser,
        enum_schemas: Mapping[Enum, Schema],
        default_conversion: DefaultConversion,
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
    ):
        super().__init__(default_conversion)
        self.aliaser = aliaser
        self.enum_aliaser = enum_aliaser
        self.enum_schemas = enum_schemas
        self.id_type = id_type
        self.is_id = is_id or (lambda t: False)
        self._cache_by_name: Dict[
            Tuple[str, Callable, Optional[str]],
            Tuple[graphql.GraphQLNonNull, Tuple[tuple, dict]],
        ] = {}

    def _recursive_result(
        self, lazy: Lazy[TypeFactory[GraphQLTp]]
    ) -> TypeFactory[GraphQLTp]:
        def factory(name: Optional[str], description: Optional[str]) -> GraphQLTp:
            cached_fact = lazy()
            return cached_fact.factory(  # type: ignore
                name or cached_fact.name, description or cached_fact.description
            )

        return TypeFactory(factory)

    def annotated(
        self, tp: AnyType, annotations: Sequence[Any]
    ) -> TypeFactory[GraphQLTp]:
        factory = super().annotated(tp, annotations)
        type_name = False
        for annotation in reversed(annotations):
            if isinstance(annotation, TypeNameFactory):
                if type_name:
                    break
                type_name = True
                factory = factory.merge(annotation.to_type_name(tp))
            if isinstance(annotation, Mapping):
                if type_name:
                    factory = factory.merge(schema=annotation.get(SCHEMA_METADATA))
        return factory

    @cache_type
    def any(self) -> TypeFactory[GraphQLTp]:
        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLScalarType:
            if name is None:
                return JSON_SCALAR
            else:
                return graphql.GraphQLScalarType(name, description=description)

        return TypeFactory(factory)

    @cache_type
    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> TypeFactory[GraphQLTp]:
        return TypeFactory(lambda *_: graphql.GraphQLList(self.visit(value_type).type))

    @cache_type
    def enum(self, cls: Type[Enum]) -> TypeFactory[GraphQLTp]:
        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLEnumType:
            return graphql.GraphQLEnumType(
                unwrap_name(name, cls),
                {
                    self.enum_aliaser(name): graphql.GraphQLEnumValue(
                        member,
                        get_description(self.enum_schemas.get(member)),
                        get_deprecated(self.enum_schemas.get(member)),
                    )
                    for name, member in cls.__members__.items()
                },
                description=description,
            )

        return TypeFactory(factory)

    @cache_type
    def literal(self, values: Sequence[Any]) -> TypeFactory[GraphQLTp]:
        from apischema.typing import Literal

        if not all(isinstance(v, str) for v in values):
            raise TypeError("apischema GraphQL only support Literal of strings")

        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLEnumType:
            return graphql.GraphQLEnumType(
                unwrap_name(name, Literal[tuple(values)]),
                dict(zip(map(self.enum_aliaser, values), values)),
                description=description,
            )

        return TypeFactory(factory)

    @cache_type
    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> TypeFactory[GraphQLTp]:
        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLScalarType:
            if name is not None:
                return graphql.GraphQLScalarType(name, description=description)
            else:
                return JSON_SCALAR

        return TypeFactory(factory)

    def object(
        self, tp: AnyType, fields: Sequence[ObjectField]
    ) -> TypeFactory[GraphQLTp]:
        raise NotImplementedError

    @cache_type
    def primitive(self, cls: Type) -> TypeFactory[GraphQLTp]:
        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLScalarType:
            assert cls is not NoneType
            if name is not None:
                return graphql.GraphQLScalarType(name, description=description)
            else:
                return GRAPHQL_PRIMITIVE_TYPES[cls]

        return TypeFactory(factory)

    def tuple(self, types: Sequence[AnyType]) -> TypeFactory[GraphQLTp]:
        raise TypeError("Tuple are not supported")

    def union(self, types: Sequence[AnyType]) -> TypeFactory[GraphQLTp]:
        factories = self._union_results((alt for alt in types if alt is not NoneType))
        if len(factories) == 1:
            factory = factories[0]
        else:
            factory = self._visited_union(factories)
        if NoneType in types or UndefinedType in types:

            def nullable(name: Optional[str], description: Optional[str]) -> GraphQLTp:
                res = factory.factory(name, description)  # type: ignore
                return res.of_type if isinstance(res, graphql.GraphQLNonNull) else res

            return replace(factory, factory=nullable)
        else:
            return factory

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Conv],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> TypeFactory[GraphQLTp]:
        if not dynamic and self.is_id(tp) or tp == ID:
            return TypeFactory(lambda *_: graphql.GraphQLNonNull(self.id_type))
        factory = super().visit_conversion(tp, conversion, dynamic, next_conversion)
        if not dynamic:
            factory = factory.merge(get_type_name(tp), get_schema(tp))
            if get_args(tp):
                factory = factory.merge(schema=get_schema(get_origin(tp)))
        return factory


FieldType = TypeVar("FieldType", graphql.GraphQLInputField, graphql.GraphQLField)


class BaseField(Generic[FieldType]):
    name: str
    ordering: Optional[Ordering]

    def items(self) -> Iterable[Tuple[str, FieldType]]:
        raise NotImplementedError


@dataclass
class NormalField(BaseField[FieldType]):
    alias: str
    name: str
    field: Lazy[FieldType]
    ordering: Optional[Ordering]

    def items(self) -> Iterable[Tuple[str, FieldType]]:
        yield self.alias, self.field()


@dataclass
class FlattenedField(BaseField[FieldType]):
    name: str
    ordering: Optional[Ordering]
    type: TypeFactory

    def items(self) -> Iterable[Tuple[str, FieldType]]:
        tp = self.type.raw_type
        if not isinstance(
            tp,
            (
                graphql.GraphQLObjectType,
                graphql.GraphQLInterfaceType,
                graphql.GraphQLInputObjectType,
            ),
        ):
            raise FlattenedError(self)
        yield from tp.fields.items()


class FlattenedError(Exception):
    def __init__(self, field: FlattenedField):
        self.field = field


def merge_fields(cls: type, fields: Sequence[BaseField]) -> Dict[str, FieldType]:
    try:
        sorted_fields = sort_by_order(
            cls, fields, lambda f: f.name, lambda f: f.ordering
        )
    except FlattenedError as err:
        raise TypeError(
            f"Flattened field {cls.__name__}.{err.field.name}"
            f" must have an object type"
        )
    return OrderedDict(chain.from_iterable(map(lambda f: f.items(), sorted_fields)))


class InputSchemaBuilder(
    SchemaBuilder[Deserialization, graphql.GraphQLInputType],
    DeserializationVisitor[TypeFactory[graphql.GraphQLInputType]],
    DeserializationObjectVisitor[TypeFactory[graphql.GraphQLInputType]],
):
    types = graphql.type.definition.graphql_input_types

    def _field(
        self, tp: AnyType, field: ObjectField
    ) -> Lazy[graphql.GraphQLInputField]:
        field_type = field.type
        field_default = graphql.Undefined if field.required else field.get_default()
        default: Any = graphql.Undefined
        # Don't put `null` default + handle Undefined as None
        if field_default in {None, Undefined}:
            field_type = Optional[field_type]
        elif field_default is not graphql.Undefined:
            try:
                default = serialize(
                    field_type,
                    field_default,
                    aliaser=self.aliaser,
                    conversion=field.deserialization,
                )
            except Exception:
                field_type = Optional[field_type]
        factory = self.visit_with_conv(field_type, field.deserialization)
        return lambda: graphql.GraphQLInputField(
            factory.type,
            default_value=default,
            description=get_description(get_field_schema(tp, field), field.type),
        )

    @cache_type
    def object(
        self, tp: AnyType, fields: Sequence[ObjectField]
    ) -> TypeFactory[graphql.GraphQLInputType]:
        visited_fields: List[BaseField] = []
        for field in fields:
            if not field.is_aggregate:
                normal_field = NormalField(
                    self.aliaser(field.alias),
                    field.name,
                    self._field(tp, field),
                    field.ordering,
                )
                visited_fields.append(normal_field)
            elif field.flattened:
                flattened_fields = FlattenedField(
                    field.name,
                    field.ordering,
                    self.visit_with_conv(field.type, field.deserialization),
                )
                visited_fields.append(flattened_fields)

        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLInputObjectType:
            name = unwrap_name(name, tp)
            if not name.endswith("Input"):
                name += "Input"
            return graphql.GraphQLInputObjectType(
                name,
                lambda: merge_fields(get_origin_or_type(tp), visited_fields),
                description,
            )

        return TypeFactory(factory)

    def _visited_union(
        self, results: Sequence[TypeFactory]
    ) -> TypeFactory[graphql.GraphQLInputType]:
        # Check must be done here too because _union_result is used by visit_conversion
        if len(results) != 1:
            raise TypeError("Union are not supported for input")
        return results[0]


Func = TypeVar("Func", bound=Callable)


class OutputSchemaBuilder(
    SchemaBuilder[Serialization, graphql.GraphQLOutputType],
    SerializationVisitor[TypeFactory[graphql.GraphQLOutputType]],
    SerializationObjectVisitor[TypeFactory[graphql.GraphQLOutputType]],
):
    types = graphql.type.definition.graphql_output_types

    def __init__(
        self,
        aliaser: Aliaser,
        enum_aliaser: Aliaser,
        enum_schemas: Mapping[Enum, Schema],
        default_conversion: DefaultConversion,
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
        union_name_factory: UnionNameFactory,
        default_deserialization: DefaultConversion,
    ):
        super().__init__(
            aliaser, enum_aliaser, enum_schemas, default_conversion, id_type, is_id
        )
        self.union_name_factory = union_name_factory
        self.input_builder = InputSchemaBuilder(
            self.aliaser,
            self.enum_aliaser,
            self.enum_schemas,
            default_deserialization,
            self.id_type,
            self.is_id,
        )
        # Share the same cache for input_builder in order to share scalar types
        self.input_builder._cache_by_name = self._cache_by_name
        self.get_flattened: Optional[Callable[[Any], Any]] = None

    def _field_serialization_method(self, field: ObjectField) -> SerializationMethod:
        return partial_serialization_method_factory(
            self.aliaser, field.serialization, self.default_conversion
        )(Optional[field.type] if field.none_as_undefined else field.type)

    def _wrap_resolve(self, resolve: Func) -> Func:
        if self.get_flattened is None:
            return resolve
        else:
            get_flattened = self.get_flattened

            def resolve_wrapper(__obj, __info, **kwargs):
                return resolve(get_flattened(__obj), __info, **kwargs)

            return cast(Func, resolve_wrapper)

    def _field(self, tp: AnyType, field: ObjectField) -> Lazy[graphql.GraphQLField]:
        field_name = field.name
        partial_serialize = self._field_serialization_method(field).serialize

        @self._wrap_resolve
        def resolve(obj, _):
            return partial_serialize(getattr(obj, field_name))

        factory = self.visit_with_conv(field.type, field.serialization)
        field_schema = get_field_schema(tp, field)
        return lambda: graphql.GraphQLField(
            factory.type,
            None,
            resolve,
            description=get_description(field_schema, field.type),
            deprecation_reason=get_deprecated(field_schema, field.type),
        )

    def _resolver(
        self, tp: AnyType, field: ResolverField
    ) -> Lazy[graphql.GraphQLField]:
        resolve = self._wrap_resolve(
            resolver_resolve(
                field.resolver,
                field.types,
                self.aliaser,
                self.input_builder.default_conversion,
                self.default_conversion,
            )
        )
        args = None
        if field.parameters is not None:
            args = {}
            for param in field.parameters:
                default: Any = graphql.Undefined
                param_type = field.types[param.name]
                if is_union_of(param_type, graphql.GraphQLResolveInfo):
                    break
                param_field = ObjectField(
                    param.name,
                    param_type,
                    param.default is Parameter.empty,
                    field.metadata.get(param.name, empty_dict),
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
                        default = serialize(
                            param_type,
                            param.default,
                            fall_back_on_any=False,
                            check_type=True,
                        )
                    except Exception:
                        param_type = Optional[param_type]
                arg_factory = self.input_builder.visit_with_conv(
                    param_type, param_field.deserialization
                )
                description = get_description(
                    get_parameter_schema(field.resolver.func, param, param_field),
                    param_field.type,
                )

                def arg_thunk(
                    arg_factory=arg_factory, default=default, description=description
                ) -> graphql.GraphQLArgument:
                    return graphql.GraphQLArgument(
                        arg_factory.type, default, description
                    )

                args[self.aliaser(param_field.alias)] = arg_thunk
        factory = self.visit_with_conv(field.types["return"], field.resolver.conversion)
        field_schema = get_method_schema(tp, field.resolver)
        return lambda: graphql.GraphQLField(
            factory.type,
            {name: arg() for name, arg in args.items()} if args else None,
            resolve,
            field.subscribe,
            get_description(field_schema),
            get_deprecated(field_schema),
        )

    def _visit_flattened(
        self, field: ObjectField
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        get_prev_flattened = (
            self.get_flattened if self.get_flattened is not None else identity
        )
        field_name = field.name
        partial_serialize = self._field_serialization_method(field).serialize

        def get_flattened(obj):
            return partial_serialize(getattr(get_prev_flattened(obj), field_name))

        with context_setter(self):
            self.get_flattened = get_flattened
            return self.visit_with_conv(field.type, field.serialization)

    @cache_type
    def object(
        self,
        tp: AnyType,
        fields: Sequence[ObjectField],
        resolvers: Sequence[ResolverField] = (),
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        cls = get_origin_or_type(tp)
        visited_fields: List[BaseField[graphql.GraphQLField]] = []
        flattened_factories = []
        for field in fields:
            if not field.is_aggregate:
                normal_field = NormalField(
                    self.aliaser(field.name),
                    field.name,
                    self._field(tp, field),
                    field.ordering,
                )
                visited_fields.append(normal_field)
            elif field.flattened:
                flattened_factory = self._visit_flattened(field)
                flattened_factories.append(flattened_factory)
                visited_fields.append(
                    FlattenedField(field.name, field.ordering, flattened_factory)
                )
        resolvers = list(resolvers)
        for resolver, types in get_resolvers(tp):
            resolver_field = ResolverField(
                resolver, types, resolver.parameters, resolver.parameters_metadata
            )
            resolvers.append(resolver_field)
        for resolver_field in resolvers:
            normal_field = NormalField(
                self.aliaser(resolver_field.resolver.alias),
                resolver_field.resolver.func.__name__,
                self._resolver(tp, resolver_field),
                resolver_field.resolver.ordering,
            )
            visited_fields.append(normal_field)

        interface_thunk = None
        interfaces = list(map(self.visit, get_interfaces(cls)))
        if interfaces or flattened_factories:

            def interface_thunk() -> Collection[graphql.GraphQLInterfaceType]:
                all_interfaces = {
                    cast(graphql.GraphQLInterfaceType, i.raw_type) for i in interfaces
                }
                for flattened_factory in flattened_factories:
                    flattened = flattened_factory.raw_type
                    if isinstance(flattened, graphql.GraphQLObjectType):
                        all_interfaces.update(flattened.interfaces)
                    elif isinstance(flattened, graphql.GraphQLInterfaceType):
                        all_interfaces.add(flattened)
                return sorted(all_interfaces, key=lambda i: i.name)

        def factory(
            name: Optional[str], description: Optional[str]
        ) -> Union[graphql.GraphQLObjectType, graphql.GraphQLInterfaceType]:
            name = unwrap_name(name, cls)
            if is_interface(cls):
                return graphql.GraphQLInterfaceType(
                    name,
                    lambda: merge_fields(cls, visited_fields),
                    interface_thunk,
                    description=description,
                )
            else:
                return graphql.GraphQLObjectType(
                    name,
                    lambda: merge_fields(cls, visited_fields),
                    interface_thunk,
                    is_type_of=lambda obj, _: isinstance(obj, cls),
                    description=description,
                )

        return TypeFactory(factory)

    def typed_dict(
        self, tp: Type, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        raise TypeError("TypedDict are not supported in output schema")

    @cache_type
    def _visited_union(
        self, results: Sequence[TypeFactory]
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLOutputType:
            types = [factory.raw_type for factory in results]
            if name is None:
                name = self.union_name_factory([t.name for t in types])
            return graphql.GraphQLUnionType(name, types, description=description)

        return TypeFactory(factory)


async_iterable_origins = set(map(get_origin, (AsyncIterable[Any], AsyncIterator[Any])))

_fake_type = cast(type, ...)


@dataclass(frozen=True)
class Operation(Generic[T]):
    function: Callable[..., T]
    alias: Optional[str] = None
    conversion: Optional[AnyConversion] = None
    error_handler: ErrorHandler = Undefined
    order: Optional[Ordering] = None
    schema: Optional[Schema] = None
    parameters_metadata: Mapping[str, Mapping] = field_(default_factory=dict)


class Query(Operation):
    pass


class Mutation(Operation):
    pass


@dataclass(frozen=True)
class Subscription(Operation[AsyncIterable]):
    resolver: Optional[Callable] = None


Op = TypeVar("Op", bound=Operation)


def operation_resolver(operation: Union[Callable, Op], op_class: Type[Op]) -> Resolver:
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
    return Resolver(
        wrapper,
        operation.alias or operation.function.__name__,
        operation.conversion,
        error_handler,
        operation.order,
        operation.schema,
        parameters,
        operation.parameters_metadata,
    )


@deprecate_kwargs({"union_ref": "union_name"})
def graphql_schema(
    *,
    query: Iterable[Union[Callable, Query]] = (),
    mutation: Iterable[Union[Callable, Mutation]] = (),
    subscription: Iterable[Union[Callable[..., AsyncIterable], Subscription]] = (),
    types: Iterable[Type] = (),
    directives: Optional[Collection[graphql.GraphQLDirective]] = None,
    description: Optional[str] = None,
    extensions: Optional[Dict[str, Any]] = None,
    aliaser: Optional[Aliaser] = to_camel_case,
    enum_aliaser: Optional[Aliaser] = str.upper,
    enum_schemas: Optional[Mapping[Enum, Schema]] = None,
    id_types: Union[Collection[AnyType], IdPredicate] = (),
    id_encoding: Tuple[
        Optional[Callable[[str], Any]], Optional[Callable[[Any], str]]
    ] = (None, None),
    union_name: UnionNameFactory = "Or".join,
    default_deserialization: DefaultConversion = None,
    default_serialization: DefaultConversion = None,
) -> graphql.GraphQLSchema:
    if aliaser is None:
        aliaser = settings.aliaser
    if enum_aliaser is None:
        enum_aliaser = lambda s: s
    if default_deserialization is None:
        default_deserialization = settings.deserialization.default_conversion
    if default_serialization is None:
        default_serialization = settings.serialization.default_conversion
    query_fields: List[ResolverField] = []
    mutation_fields: List[ResolverField] = []
    subscription_fields: List[ResolverField] = []
    for operations, op_class, fields in [
        (query, Query, query_fields),
        (mutation, Mutation, mutation_fields),
    ]:
        for operation in operations:
            resolver = operation_resolver(operation, op_class)
            resolver_field = ResolverField(
                resolver,
                resolver.types(),
                resolver.parameters,
                resolver.parameters_metadata,
            )
            fields.append(resolver_field)
    for sub_op in subscription:
        if not isinstance(sub_op, Subscription):
            sub_op = Subscription(sub_op)  # type: ignore
        sub_parameters: Sequence[Parameter]
        if sub_op.resolver is not None:
            subscriber2 = operation_resolver(sub_op, Subscription)
            _, *sub_parameters = resolver_parameters(sub_op.resolver, check_first=False)
            resolver = Resolver(
                sub_op.resolver,
                sub_op.alias or sub_op.resolver.__name__,
                sub_op.conversion,
                subscriber2.error_handler,
                sub_op.order,
                sub_op.schema,
                sub_parameters,
                sub_op.parameters_metadata,
            )
            sub_types = resolver.types()
            subscriber = replace(subscriber2, error_handler=None)
            subscribe = resolver_resolve(
                subscriber,
                subscriber.types(),
                aliaser,
                default_deserialization,
                default_serialization,
                serialized=False,
            )
        else:
            subscriber2 = operation_resolver(sub_op, Subscription)
            resolver = Resolver(
                lambda _: _,
                subscriber2.alias,
                sub_op.conversion,
                subscriber2.error_handler,
                sub_op.order,
                sub_op.schema,
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
                subscriber,
                sub_types,
                aliaser,
                default_deserialization,
                default_serialization,
                serialized=False,
            )
            sub_types = {**sub_types, "return": resolver.return_type(event_type)}

        resolver_field = ResolverField(
            resolver, sub_types, sub_parameters, sub_op.parameters_metadata, subscribe
        )
        subscription_fields.append(resolver_field)

    is_id = as_predicate(id_types)
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

    output_builder = OutputSchemaBuilder(
        aliaser,
        enum_aliaser,
        enum_schemas or {},
        default_serialization,
        id_type,
        is_id,
        union_name,
        default_deserialization,
    )

    def root_type(
        name: str, fields: Sequence[ResolverField]
    ) -> Optional[graphql.GraphQLObjectType]:
        if not fields:
            return None
        tp, type_name = type(name, (), {}), TypeName(graphql=name)
        return output_builder.object(tp, (), fields).merge(type_name, None).raw_type

    return graphql.GraphQLSchema(
        query=root_type("Query", query_fields),
        mutation=root_type("Mutation", mutation_fields),
        subscription=root_type("Subscription", subscription_fields),
        types=[output_builder.visit(cls).raw_type for cls in types],
        directives=directives,
        description=description,
        extensions=extensions,
    )
