from collections import ChainMap
from contextlib import suppress
from dataclasses import Field, dataclass
from enum import Enum
from inspect import Parameter
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
    Dict,
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

from graphql import (
    DEFAULT_DEPRECATION_REASON,
    GraphQLArgument,
    GraphQLBoolean,
    GraphQLDirective,
    GraphQLEnumType,
    GraphQLField,
    GraphQLFieldMap,
    GraphQLFloat,
    GraphQLID,
    GraphQLInputField,
    GraphQLInt,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLString,
    GraphQLType,
    GraphQLUnionType,
    Undefined as GraphQLUndefined,
)
from graphql.type.definition import GraphQLInputObjectType, Thunk

from apischema import serialize
from apischema.aliases import Aliaser
from apischema.conversions import Conversions, Deserialization, Serialization
from apischema.conversions.visitor import (
    Conv,
)
from apischema.dataclass_utils import (
    check_merged_class,
    get_alias,
    get_default,
    is_required,
)
from apischema.graphql.interfaces import is_interface
from apischema.graphql.resolvers import (
    ResolverArgument,
    get_resolvers,
    resolver_types_and_wrapper,
)
from apischema.json_schema.generation.visitor import (
    DeserializationSchemaVisitor,
    SchemaVisitor,
    SerializationSchemaVisitor,
)
from apischema.json_schema.refs import get_ref, schema_ref
from apischema.json_schema.schema import Schema, get_schema, merge_schema
from apischema.metadata.keys import (
    MERGED_METADATA,
    PROPERTIES_METADATA,
    SCHEMA_METADATA,
    check_metadata,
)
from apischema.skip import filter_skipped
from apischema.types import AnyType, NoneType
from apischema.typing import get_args, get_origin
from apischema.utils import Undefined, is_hashable, map_values, to_camel_case, type_name

JsonScalar = GraphQLScalarType(
    "JSON",
    specified_by_url="http://www.ecma-international.org/publications/files/ECMA-ST/ECMA-404.pdf",  # noqa: E501
)
GRAPHQL_PRIMITIVE_TYPES = {
    int: GraphQLInt,
    float: GraphQLFloat,
    str: GraphQLString,
    bool: GraphQLBoolean,
}


class MissingRef(Exception):
    pass


class Nullable(Exception):
    pass


def ref_or_name(cls: AnyType) -> str:
    return get_ref(cls) or type_name(cls)


T = TypeVar("T")
Lazy = Callable[[], T]


def exec_thunk(thunk: Thunk[GraphQLType], *, non_null=None) -> Any:
    result = thunk if isinstance(thunk, GraphQLType) else thunk()
    if non_null is True and not isinstance(result, GraphQLNonNull):
        return GraphQLNonNull(result)  # type: ignore
    if non_null is False and isinstance(result, GraphQLNonNull):
        return result.of_type
    return result


U = TypeVar("U")


def merged_dict(*mapping: Mapping[T, U]) -> Dict[T, U]:
    return dict(ChainMap(*reversed(mapping)))


@dataclass(frozen=True)
class ObjectField:
    name: str
    type: AnyType
    default: Any = GraphQLUndefined
    conversions: Optional[Conversions] = None
    alias: Optional[str] = None
    description: Optional[str] = None
    deprecated: Optional[str] = None
    resolve: Optional[Callable] = None
    arguments: Optional[Collection[ResolverArgument]] = None
    subscribe: Optional[Callable] = None

    def apply_aliaser(self, aliaser: Aliaser) -> str:
        return aliaser(self.alias or self.name)


IdPredicate = Callable[[AnyType], bool]
GenericRefFactory = Callable[[AnyType], str]
UnionRefFactory = Callable[[Sequence[str]], str]


class SchemaBuilder(SchemaVisitor[Conv, Thunk[GraphQLType]]):
    def __init__(
        self,
        aliaser: Optional[Aliaser],
        is_id: Optional[IdPredicate],
        generic_ref_factory: Optional[GenericRefFactory],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__()
        self.aliaser = aliaser or (lambda s: s)
        self.is_id = is_id or (lambda t: False)
        self.generic_ref_factory = generic_ref_factory
        self.union_ref_factory = union_ref_factory
        self._cache: Dict[Any, Thunk[GraphQLType]] = {}
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

    def annotated(self, cls: AnyType, annotations: Sequence[Any]) -> Thunk[GraphQLType]:
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

    def any(self) -> Thunk[GraphQLType]:
        return JsonScalar

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Thunk[GraphQLType]:
        value_thunk = self.visit(value_type)
        return lambda: GraphQLList(exec_thunk(value_thunk))

    def _object_field(self, field: Field, field_type: AnyType) -> ObjectField:
        schema: Optional[Schema] = field.metadata.get(SCHEMA_METADATA)
        description, deprecated = None, None
        default: Any = GraphQLUndefined
        if schema is not None and schema.annotations is not None:
            description = schema.annotations.description
            if schema.annotations.deprecated:
                if isinstance(schema.annotations.deprecated, str):
                    deprecated = schema.annotations.deprecated
                else:
                    deprecated = DEFAULT_DEPRECATION_REASON
            if schema.annotations.default is not Undefined and not is_required(field):
                default = schema.annotations.default
        field_type, conversions = self._field_conversions(field, field_type)
        if not is_required(field) and default is GraphQLUndefined:
            with suppress(Exception):
                default = serialize(get_default(field), conversions=conversions)
        return ObjectField(
            field.name,
            field_type,
            default=default,
            conversions=conversions,
            alias=get_alias(field),
            description=description,
            deprecated=deprecated,
        )

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Thunk[GraphQLType]:
        types = dict(types)
        object_fields: List[ObjectField] = []
        merged_fields: Dict[str, AnyType] = {}
        for field in self._dataclass_fields(fields, init_vars):
            check_metadata(field)
            metadata = field.metadata
            if MERGED_METADATA in metadata:
                check_merged_class(types[field.name])
                merged_fields[field.name] = types[field.name]
            elif PROPERTIES_METADATA in metadata:
                continue
            else:
                object_fields.append(self._object_field(field, types[field.name]))
        return self.object(cls, object_fields, merged_fields)

    def enum(self, cls: Type[Enum]) -> Thunk[GraphQLType]:
        return self.literal([elt.value for elt in cls])

    def generic(self, cls: AnyType) -> Thunk[GraphQLType]:
        if self.generic_ref_factory is None:
            raise MissingRef
        self._ref = self.generic_ref_factory(cls)
        return super().generic(cls)

    def literal(self, values: Sequence[Any]) -> Thunk[GraphQLType]:
        if not all(isinstance(v, str) for v in values):
            raise TypeError("Apischema GraphQL only support Enum/Literal of strings")
        name, description = self._ref_and_desc
        return GraphQLEnumType(name, dict(zip(values, values)), description=description)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Thunk[GraphQLType]:
        try:
            name, description = self._ref_and_desc
            return GraphQLScalarType(name, description=description)
        except MissingRef:
            return JsonScalar

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> Thunk[GraphQLType]:
        fields = []
        for field_name, field_type in types.items():
            default = GraphQLUndefined
            if field_name in defaults:
                with suppress(Exception):
                    default = serialize(defaults[field_name])
            fields.append(ObjectField(field_name, field_type, default))
        return self.object(cls, fields)

    def new_type(self, cls: Type, super_type: AnyType) -> Thunk[GraphQLType]:
        return self.visit_with_schema(super_type, self._ref, self._schema)

    def object(
        self,
        cls: Type,
        fields: Collection[ObjectField],
        merged_fields: Mapping[str, Thunk[GraphQLType]] = None,
    ) -> Thunk[GraphQLType]:
        raise NotImplementedError()

    def primitive(self, cls: Type) -> Thunk[GraphQLType]:
        if cls is NoneType:
            raise Nullable
        try:
            name, description = self._ref_and_desc
            return GraphQLScalarType(name, description=description)
        except MissingRef:
            return GRAPHQL_PRIMITIVE_TYPES[cls]

    def tuple(self, types: Sequence[AnyType]) -> Thunk[GraphQLType]:
        raise TypeError("Tuple are not supported")

    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool
    ) -> Thunk[GraphQLType]:
        raise TypeError("TyedDict are not supported")

    def union(self, alternatives: Sequence[AnyType]) -> Thunk[GraphQLType]:
        alternatives = list(filter_skipped(alternatives, schema_only=True))
        results = []
        filtered_alt = []
        for alt in alternatives:
            try:
                results.append(self.visit(alt))
                filtered_alt.append(alt)
            except Nullable:
                self._non_null = False
        if not results:
            raise TypeError("Empty union")
        return self._union_result(results)

    def visit_with_schema(
        self, cls: AnyType, ref: Optional[str], schema: Optional[Schema]
    ) -> Thunk[GraphQLType]:
        if self.is_id(cls):
            return GraphQLNonNull(GraphQLID)
        if is_hashable(cls) and not self.is_extra_conversions(cls):
            ref, schema = ref or get_ref(cls), merge_schema(get_schema(cls), schema)
        else:
            schema, ref = None, None
        ref_save, schema_save = self._ref, self._schema
        self._ref, self._schema = ref, schema
        try:
            self._non_null = True
            result = super().visit(cls)
            non_null = self._non_null
            return lambda: exec_thunk(result, non_null=non_null)
        except MissingRef:
            raise TypeError(f"Missing ref for type {cls}")
        finally:
            self._ref, self._schema = ref_save, schema_save

    def visit_not_conversion(self, cls: AnyType) -> Thunk[GraphQLType]:
        key = self._resolve_type_vars(cls), self._ref, self._schema
        if key in self._cache:
            return self._cache[key]
        cache = None

        def rec_sentinel() -> GraphQLType:
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
        # if key not in self._cache:
        #     thunk = super().visit_not_conversion(cls)
        #     if isinstance(thunk, GraphQLType):
        #         self._cache[key] = thunk
        #     else:
        #         self._cache[key] = lru_cache(maxsize=1)(thunk)
        # return self._cache[key]

    def visit(self, cls: AnyType) -> Thunk[GraphQLType]:
        return self.visit_with_schema(cls, None, None)


class InputSchemaBuilder(
    DeserializationSchemaVisitor[Thunk[GraphQLType]], SchemaBuilder[Deserialization]
):
    def _field(self, field: ObjectField) -> Tuple[str, Lazy[GraphQLInputField]]:
        alias = field.apply_aliaser(self.aliaser)
        field_type = self.visit_with_conversions(field.type, field.conversions)
        return alias, lambda: GraphQLInputField(
            exec_thunk(field_type),
            default_value=field.default,
            description=field.description,
            out_name=field.name,
        )

    def object(
        self,
        cls: Type,
        fields: Collection[ObjectField],
        merged_fields: Mapping[str, AnyType] = None,
    ) -> Thunk[GraphQLType]:
        name, description = self._ref_and_desc
        name = name if name.endswith("Input") else name + "Input"
        visited_fields = dict(map(self._field, fields))
        visited_merged = map_values(self.visit, merged_fields or {})
        return lambda: GraphQLInputObjectType(
            name, lambda: merge_fields(cls, visited_fields, visited_merged), description
        )

    def _union_result(
        self, results: Iterable[Thunk[GraphQLType]]
    ) -> Thunk[GraphQLType]:
        results = list(results)  # Execute the iteration
        if len(results) == 1:
            return results[0]
        raise TypeError("Union are not supported for input")


class OutputSchemaBuilder(
    SerializationSchemaVisitor[Thunk[GraphQLType]], SchemaBuilder[Serialization]
):
    def __init__(
        self,
        aliaser: Optional[Aliaser],
        is_id: Optional[IdPredicate],
        generic_ref_factory: Optional[GenericRefFactory],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__(aliaser, is_id, generic_ref_factory, union_ref_factory)
        self.input_builder = InputSchemaBuilder(
            aliaser, is_id, generic_ref_factory, union_ref_factory
        )

    def _field(self, field: ObjectField) -> Tuple[str, Lazy[GraphQLField]]:
        alias = field.apply_aliaser(self.aliaser)
        if field.resolve is not None:
            resolve = field.resolve
        else:
            resolve = lambda obj, _: getattr(obj, field.name)  # noqa: E731
        field_type = self.visit_with_conversions(field.type, field.conversions)
        args = None
        if field.arguments is not None:
            args = {}
            for arg in field.arguments:
                arg_type = self.input_builder.visit(arg.type)
                default = GraphQLUndefined
                if arg.default not in {Parameter.empty, Undefined, GraphQLUndefined}:
                    with suppress(Exception):
                        default = serialize(arg.default)
                args[
                    self.aliaser(arg.name)
                ] = lambda arg_type=arg_type, default=default: GraphQLArgument(
                    exec_thunk(arg_type), default, out_name=arg.name
                )
        return alias, lambda: GraphQLField(
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
        merged_fields: Mapping[str, AnyType] = None,
    ) -> Thunk[GraphQLType]:
        fields_and_resolvers = list(fields)
        try:
            name, description = self._ref_and_desc
        except MissingRef:
            if cls.__name__ not in ("Query", "Mutation", "Subscription"):
                raise
            name, description = cls.__name__, self._description
        resolvers = ChainMap(*map(get_resolvers, cls.__mro__))
        for resolver_name, resolver in resolvers.items():
            ret, arguments, wrapper = resolver_types_and_wrapper(resolver.func)
            resolver_field = ObjectField(
                resolver_name,
                ret,
                resolve=wrapper,
                arguments=arguments,
            )
            fields_and_resolvers.append(resolver_field)
        visited_merged = map_values(self.visit, merged_fields or {})

        def deref_merged_field(merged_attr: str, field: GraphQLField) -> GraphQLField:
            def resolve(obj, info, **kwargs):
                return field.resolve(getattr(obj, merged_attr), info, **kwargs)

            return GraphQLField(**ChainMap(dict(resolve=resolve), field.to_kwargs()))

        def field_thunk() -> GraphQLFieldMap:
            return merge_fields(
                cls,
                dict(map(self._field, fields_and_resolvers)),
                visited_merged,
                deref_merged_field,
            )

        interfaces = list(map(self.visit, filter(is_interface, cls.__mro__[1:])))
        interface_thunk = None
        if interfaces:

            def interface_thunk() -> Collection[GraphQLInterfaceType]:
                result = {exec_thunk(i, non_null=False) for i in interfaces}
                for merged_thunk in visited_merged:
                    merged = cast(
                        Union[GraphQLObjectType, GraphQLInterfaceType],
                        exec_thunk(merged_thunk, non_null=False),
                    )
                    result.update(merged.interfaces)
                return sorted(result, key=lambda i: i.name)

        if is_interface(cls):
            return lambda: GraphQLInterfaceType(
                name,
                field_thunk,
                interface_thunk,
                description=description,
            )

        else:
            return lambda: GraphQLObjectType(
                name,
                field_thunk,
                interface_thunk,
                is_type_of=lambda obj, _: isinstance(obj, cls),
                description=description,
            )

    def _union_result(
        self, results: Iterable[Thunk[GraphQLType]]
    ) -> Thunk[GraphQLType]:
        results = list(results)  # Execute the iteration
        if len(results) == 1:
            return results[0]
        name, description = self._ref, self._description
        if name is None and self.union_ref_factory is None:
            raise MissingRef

        def thunk() -> GraphQLUnionType:
            types = [exec_thunk(res, non_null=False) for res in results]
            if name is None:
                assert self.union_ref_factory is not None
                computed_name = self.union_ref_factory([t.name for t in types])
            else:
                computed_name = name
            return GraphQLUnionType(computed_name, types, description=description)

        return thunk


FieldType = TypeVar("FieldType", GraphQLInputField, GraphQLField)


def merge_fields(
    cls: Type,
    fields: Mapping[str, Lazy[FieldType]],
    merged_types: Mapping[str, Thunk[GraphQLType]],
    merged_field_modifier: Callable[[str, FieldType], FieldType] = None,
) -> Dict[str, FieldType]:
    all_merged_fields: Dict[str, FieldType] = {}
    for merged_name, merged_thunk in merged_types.items():
        merged_type = exec_thunk(merged_thunk, non_null=False)
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


AwaitableOrNot = Union[Awaitable[T], T]
Subscribe = Callable[..., AwaitableOrNot[AsyncIterable]]
NamedOrNot = Union[T, Tuple[str, T]]

async_iterable_origins = set(map(get_origin, (AsyncIterable[Any], AsyncIterator[Any])))


def graphql_schema(
    query: Iterable[NamedOrNot[Callable]] = (),
    mutation: Iterable[NamedOrNot[Callable]] = (),
    subscription: Iterable[
        NamedOrNot[Union[Subscribe, Tuple[Subscribe, Callable]]]
    ] = (),
    types: Iterable[Type] = (),
    aliaser: Aliaser = to_camel_case,
    is_id: IdPredicate = None,
    generic_ref_factory: GenericRefFactory = None,
    union_ref_factory: UnionRefFactory = None,
    directives: Optional[Collection[GraphQLDirective]] = None,
    description: Optional[str] = None,
    extensions: Optional[Dict[str, Any]] = None,
) -> GraphQLSchema:
    query_fields: List[ObjectField] = []
    mutation_fields: List[ObjectField] = []
    subscription_fields: List[ObjectField] = []
    for endpoints, fields in [(query, query_fields), (mutation, mutation_fields)]:
        for resolve in endpoints:
            if isinstance(resolve, tuple):
                name, resolve = resolve
            else:
                name = resolve.__name__
            ret, arguments, wrapper = resolver_types_and_wrapper(resolve)
            fields.append(ObjectField(name, ret, resolve=wrapper, arguments=arguments))
    for subscribe in subscription:
        if isinstance(subscribe, tuple) and isinstance(subscribe[0], str):
            name, subscribe = subscribe  # type: ignore
        else:
            name = None  # type: ignore
        if isinstance(subscribe, tuple):
            subscribe, resolve = subscribe  # type: ignore
            name = name or resolve.__name__  # type: ignore
            ret, resolve_arguments, resolve_wrapper = resolver_types_and_wrapper(resolve)  # type: ignore # noqa: E501
            _, _, subscribe_wrapper = resolver_types_and_wrapper(subscribe)  # type: ignore # noqa: E501
        else:
            resolve_wrapper = lambda obj, *args, **kwargs: obj  # noqa: E731
            name = name or subscribe.__name__
            ret, arguments, subscribe_wrapper = resolver_types_and_wrapper(subscribe)
            if get_origin(ret) not in async_iterable_origins:
                raise TypeError(
                    "Subscriptions must return an AsyncIterable/AsyncIterator"
                )
            ret = get_args(ret)[0]
        subscription_fields.append(
            ObjectField(
                name,
                ret,
                resolve=resolve_wrapper,
                arguments=arguments,
                subscribe=subscribe_wrapper,
            )
        )
    builder = OutputSchemaBuilder(
        aliaser, is_id, generic_ref_factory, union_ref_factory
    )

    def root_type(
        name: str, fields: Collection[ObjectField]
    ) -> Optional[GraphQLObjectType]:
        if not fields:
            return None
        return exec_thunk(builder.object(type(name, (), {}), fields), non_null=False)

    return GraphQLSchema(
        root_type("Query", query_fields),
        root_type("Mutation", mutation_fields),
        root_type("Subscription", subscription_fields),
        [exec_thunk(builder.visit(cls), non_null=False) for cls in types],
        directives,
        description,
        extensions,
    )
