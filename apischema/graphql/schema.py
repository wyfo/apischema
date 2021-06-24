from dataclasses import dataclass, field as field_, replace
from enum import Enum
from functools import wraps
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

from apischema import settings
from apischema.aliases import Aliaser
from apischema.conversions import identity
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.visitor import (
    CachedConversionsVisitor,
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
from apischema.metadata.keys import SCHEMA_METADATA
from apischema.objects import ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.schemas import Schema, get_schema, merge_schema
from apischema.serialization import SerializationMethod, serialize
from apischema.serialization.serialized_methods import ErrorHandler
from apischema.type_names import TypeName, TypeNameFactory, get_type_name
from apischema.types import AnyType, NoneType, OrderedDict, Undefined, UndefinedType
from apischema.typing import get_args, get_origin, is_annotated
from apischema.utils import (
    Lazy,
    context_setter,
    empty_dict,
    get_args2,
    get_origin2,
    get_origin_or_type,
    is_union_of,
    literal_values,
    sort_by_annotations_position,
    to_camel_case,
)

JsonScalar = graphql.GraphQLScalarType(
    "JSON",
    specified_by_url="http://www.ecma-international.org/publications/files/ECMA-ST/ECMA-404.pdf",
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
    alias: str
    resolver: Resolver
    types: Mapping[str, AnyType]
    parameters: Sequence[Parameter]
    metadata: Mapping[str, Mapping]
    subscribe: Optional[Callable] = None

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
                return graphql.GraphQLNonNull(factory.factory(name, description))  # type: ignore
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
    CachedConversionsVisitor[Conv, TypeFactory[GraphQLTp]],
    ObjectVisitor[TypeFactory[GraphQLTp]],
):
    types: Tuple[Type[graphql.GraphQLType], ...]

    def __init__(
        self,
        aliaser: Aliaser,
        default_conversion: DefaultConversion,
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
    ):
        super().__init__(default_conversion)
        self.aliaser = aliaser
        self.id_type = id_type
        self.is_id = is_id or (lambda t: False)
        self._cache_by_name: Dict[
            Tuple[str, Callable, Optional[str]], Tuple[GraphQLTp, Tuple[tuple, dict]]
        ] = {}

    def _cache_result(
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
        return factory  # type: ignore

    @cache_type
    def any(self) -> TypeFactory[GraphQLTp]:
        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLScalarType:
            if name is None:
                return JsonScalar
            else:
                return graphql.GraphQLScalarType(name, description=description)

        return TypeFactory(factory)

    @cache_type
    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> TypeFactory[GraphQLTp]:
        return TypeFactory(lambda *_: graphql.GraphQLList(self.visit(value_type).type))

    def _visit_flattened(self, field: ObjectField) -> TypeFactory[GraphQLTp]:
        raise NotImplementedError

    @cache_type
    def _literal(self, values: Sequence[Any], tp: AnyType) -> TypeFactory[GraphQLTp]:
        if not all(isinstance(v, str) for v in literal_values(values)):
            raise TypeError("apischema GraphQL only support Enum/Literal of strings")

        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLEnumType:
            return graphql.GraphQLEnumType(
                unwrap_name(name, tp),
                dict(zip(values, values)),
                description=description,
            )

        return TypeFactory(factory)

    def enum(self, cls: Type[Enum]) -> TypeFactory[GraphQLTp]:
        return self._literal([elt.value for elt in cls], cls)

    def literal(self, values: Sequence[Any]) -> TypeFactory[GraphQLTp]:
        from apischema.typing import Literal

        return self._literal(values, Literal[tuple(values)])  # type: ignore

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
                return JsonScalar

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

    def union(self, alternatives: Sequence[AnyType]) -> TypeFactory[GraphQLTp]:
        factories = [
            self.visit(alt)
            for alt in alternatives
            if alt not in (NoneType, UndefinedType)
        ]
        if not factories:
            raise TypeError("Empty union")
        if len(factories) == 1:
            factory = factories[0]
        else:
            factory = self._union_result(factories)
        if len(factories) != len(alternatives):

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
        return factory  # type: ignore


FieldType = TypeVar("FieldType", graphql.GraphQLInputField, graphql.GraphQLField)


def merge_fields(
    cls: Type,
    fields: Mapping[str, Lazy[FieldType]],
    flattened_types: Mapping[str, TypeFactory],
) -> Dict[str, FieldType]:
    all_flattened_fields: Dict[str, FieldType] = {}
    for flattened_name, flattened_factory in flattened_types.items():
        flattened_type = flattened_factory.raw_type
        if not isinstance(
            flattened_type,
            (
                graphql.GraphQLObjectType,
                graphql.GraphQLInterfaceType,
                graphql.GraphQLInputObjectType,
            ),
        ):
            raise TypeError(
                f"Flattened field {cls.__name__}.{flattened_name} must have an object type"
            )
        flattened_fields: Mapping[str, FieldType] = flattened_type.fields
        if flattened_fields.keys() & all_flattened_fields.keys() & fields.keys():
            raise TypeError(f"Conflict in flattened fields of {cls}")
        all_flattened_fields.update(flattened_fields)
    return {**{name: field() for name, field in fields.items()}, **all_flattened_fields}


class InputSchemaBuilder(
    SchemaBuilder[Deserialization, graphql.GraphQLInputType],
    DeserializationVisitor[TypeFactory[graphql.GraphQLInputType]],
    DeserializationObjectVisitor[TypeFactory[graphql.GraphQLInputType]],
):
    types = graphql.type.definition.graphql_input_types

    def _visit_flattened(
        self, field: ObjectField
    ) -> TypeFactory[graphql.GraphQLInputType]:
        return self.visit_with_conv(field.type, field.deserialization)

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
                    field_type,
                    field_default,
                    aliaser=self.aliaser,
                    conversion=field.deserialization,
                )
            except Exception:
                field_type = Optional[field_type]
        factory = self.visit_with_conv(field_type, field.deserialization)
        return lambda: graphql.GraphQLInputField(
            factory.type,  # type: ignore
            default_value=default,
            description=get_description(field.schema, field.type),
            extensions={field.name: ""},
        )

    @cache_type
    def object(
        self, tp: AnyType, fields: Sequence[ObjectField]
    ) -> TypeFactory[graphql.GraphQLInputType]:
        visited_fields = {
            self.aliaser(f.alias): self._field(f) for f in fields if not f.is_aggregate
        }
        flattened_types = {
            f.name: self._visit_flattened(f) for f in fields if f.flattened
        }

        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLInputObjectType:
            name = unwrap_name(name, tp)
            if not name.endswith("Input"):
                name += "Input"
            return graphql.GraphQLInputObjectType(
                name,
                lambda: merge_fields(tp, visited_fields, flattened_types),
                description,
            )

        return TypeFactory(factory)

    def _union_result(
        self, results: Iterable[TypeFactory]
    ) -> TypeFactory[graphql.GraphQLInputType]:
        results = list(results)
        # Check must be done here too because _union_result is used by visit_conversion
        if len(results) == 1:
            return results[0]
        else:
            raise TypeError("Union are not supported for input")


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
        default_conversion: DefaultConversion,
        id_type: graphql.GraphQLScalarType,
        is_id: Optional[IdPredicate],
        union_name_factory: UnionNameFactory,
        default_deserialization: DefaultConversion,
    ):
        super().__init__(aliaser, default_conversion, id_type, is_id)
        self.union_name_factory = union_name_factory
        self.input_builder = InputSchemaBuilder(
            self.aliaser, default_deserialization, self.id_type, self.is_id
        )
        # Share the same cache for input_builder in order to share
        self.input_builder._cache_by_name = self._cache_by_name
        self.get_flattened: Optional[Callable[[Any], Any]] = None

    def _field_serialization_method(self, field: ObjectField) -> SerializationMethod:
        return partial_serialization_method_factory(
            self.aliaser, field.serialization, self.default_conversion
        )(field.type)

    def _wrap_resolve(self, resolve: Func) -> Func:
        if self.get_flattened is None:
            return resolve
        else:
            get_flattened = self.get_flattened

            def resolve_wrapper(__obj, __info, **kwargs):
                return resolve(get_flattened(__obj), __info, **kwargs)

            return cast(Func, resolve_wrapper)

    def _field(self, field: ObjectField) -> Lazy[graphql.GraphQLField]:
        field_name = field.name
        partial_serialize = self._field_serialization_method(field)

        @self._wrap_resolve
        def resolve(obj, _):
            return partial_serialize(getattr(obj, field_name))

        factory = self.visit_with_conv(field.type, field.serialization)
        return lambda: graphql.GraphQLField(
            factory.type,
            None,
            resolve,
            description=get_description(field.schema, field.type),
            deprecation_reason=get_deprecated(field.schema, field.type),
        )

    def _resolver(self, field: ResolverField) -> Lazy[graphql.GraphQLField]:
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
                description = get_description(param_field.schema, param_field.type)

                def arg_thunk(
                    arg_factory=arg_factory, default=default, description=description
                ) -> graphql.GraphQLArgument:
                    return graphql.GraphQLArgument(
                        arg_factory.type, default, description
                    )

                args[self.aliaser(param_field.alias)] = arg_thunk
        factory = self.visit_with_conv(field.type, field.resolver.conversion)
        return lambda: graphql.GraphQLField(
            factory.type,  # type: ignore
            {name: arg() for name, arg in args.items()} if args else None,
            resolve,
            field.subscribe,
            field.description,
            field.deprecated,
        )

    def _visit_flattened(
        self, field: ObjectField
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        get_prev_flattened = (
            self.get_flattened if self.get_flattened is not None else identity
        )
        field_name = field.name
        partial_serialize = self._field_serialization_method(field)

        def get_flattened(obj):
            return partial_serialize(getattr(get_prev_flattened(obj), field_name))

        with context_setter(self) as setter:
            setter.get_flattened = get_flattened
            return self.visit_with_conv(field.type, field.serialization)

    @cache_type
    def object(
        self,
        tp: AnyType,
        fields: Sequence[ObjectField],
        resolvers: Sequence[ResolverField] = (),
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        cls = get_origin_or_type(tp)
        all_fields = {f.alias: self._field(f) for f in fields if not f.is_aggregate}
        name_by_aliases = {f.alias: f.name for f in fields}
        all_fields.update({r.alias: self._resolver(r) for r in resolvers})
        name_by_aliases.update({r.alias: r.resolver.func.__name__ for r in resolvers})
        for alias, (resolver, types) in get_resolvers(tp).items():
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
        flattened_types = {
            f.name: self._visit_flattened(f) for f in fields if f.flattened
        }

        def field_thunk() -> graphql.GraphQLFieldMap:
            return merge_fields(cls, visited_fields, flattened_types)

        interfaces = list(map(self.visit, get_interfaces(cls)))
        interface_thunk = None
        if interfaces:

            def interface_thunk() -> Collection[graphql.GraphQLInterfaceType]:
                result = {
                    cast(graphql.GraphQLInterfaceType, i.raw_type) for i in interfaces
                }
                for flattened_factory in flattened_types.values():
                    flattened = cast(
                        Union[graphql.GraphQLObjectType, graphql.GraphQLInterfaceType],
                        flattened_factory.raw_type,
                    )
                    result.update(flattened.interfaces)
                return sorted(result, key=lambda i: i.name)

        def factory(
            name: Optional[str], description: Optional[str]
        ) -> Union[graphql.GraphQLObjectType, graphql.GraphQLInterfaceType]:
            name = unwrap_name(name, cls)
            if is_interface(cls):
                return graphql.GraphQLInterfaceType(
                    name, field_thunk, interface_thunk, description=description
                )
            else:
                return graphql.GraphQLObjectType(
                    name,
                    field_thunk,
                    interface_thunk,
                    is_type_of=lambda obj, _: isinstance(obj, cls),
                    description=description,
                )

        return TypeFactory(factory)

    def typed_dict(
        self, tp: Type, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        raise TypeError("TypedDict are not supported in output schema")

    def _union_result(
        self, factories: Iterable[TypeFactory]
    ) -> TypeFactory[graphql.GraphQLOutputType]:
        factories = list(factories)  # Execute the iteration (tuple to be hashable)

        def factory(
            name: Optional[str], description: Optional[str]
        ) -> graphql.GraphQLOutputType:
            types = [factory.raw_type for factory in factories]
            if name is None:
                name = self.union_name_factory([t.name for t in types])
            cache_key = (name, self._union_result, description)
            if cache_key not in self._cache_by_name:
                self._cache_by_name[cache_key] = graphql.GraphQLNonNull(
                    graphql.GraphQLUnionType(name, types, description=description)
                ), ((), {})
            return self._cache_by_name[cache_key][0]

        return TypeFactory(factory)


async_iterable_origins = set(map(get_origin, (AsyncIterable[Any], AsyncIterator[Any])))

_fake_type = cast(type, ...)


@dataclass(frozen=True)
class Operation(Generic[T]):
    function: Callable[..., T]
    alias: Optional[str] = None
    conversion: Optional[AnyConversion] = None
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
        operation.conversion,
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
    aliaser: Optional[Aliaser] = to_camel_case,
    id_types: Union[Collection[AnyType], IdPredicate] = None,
    id_encoding: Tuple[
        Optional[Callable[[str], Any]], Optional[Callable[[Any], str]]
    ] = (None, None),
    # TODO deprecate union_ref parameter
    union_ref: UnionNameFactory = "Or".join,
    union_name: UnionNameFactory = "Or".join,
    default_deserialization: DefaultConversion = None,
    default_serialization: DefaultConversion = None,
) -> graphql.GraphQLSchema:
    if aliaser is None:
        aliaser = settings.aliaser
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
                sub_op.conversion,
                sub_op.schema,
                subscriber2.error_handler,
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
            alias, subscriber2 = operation_resolver(sub_op, Subscription)
            resolver = Resolver(
                lambda _: _,
                sub_op.conversion,
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
                subscriber,
                sub_types,
                aliaser,
                default_deserialization,
                default_serialization,
                serialized=False,
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

    output_builder = OutputSchemaBuilder(
        aliaser,
        default_serialization,
        id_type,
        is_id,
        union_name or union_ref,
        default_deserialization,
    )

    def root_type(
        name: str, fields: Sequence[ResolverField]
    ) -> Optional[graphql.GraphQLObjectType]:
        if not fields:
            return None
        tp, type_name = type(name, (), {}), TypeName(graphql=name)
        return output_builder.object(tp, (), fields).merge(type_name, None).raw_type  # type: ignore

    return graphql.GraphQLSchema(
        query=root_type("Query", query_fields),
        mutation=root_type("Mutation", mutation_fields),
        subscription=root_type("Subscription", subscription_fields),
        types=[output_builder.visit(cls).raw_type for cls in types],  # type: ignore
        directives=directives,
        description=description,
        extensions=extensions,
    )
