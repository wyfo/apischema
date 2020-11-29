from collections import ChainMap
from contextlib import suppress
from dataclasses import Field, InitVar, dataclass
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

import graphql

from apischema import serialize
from apischema.aliases import Aliaser
from apischema.conversions import Conversions, Deserialization, Serialization
from apischema.conversions.visitor import Conv
from apischema.dataclass_utils import (
    check_merged_class,
    get_alias,
    get_default,
    is_required,
)
from apischema.graphql.interfaces import get_interfaces, is_interface
from apischema.graphql.resolvers import INFO_TYPES, resolver_resolve
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
from apischema.resolvers import (
    MissingFirstParameter,
    Resolver,
    get_resolvers,
    resolver_parameters,
)
from apischema.skip import filter_skipped
from apischema.types import AnyType, NoneType
from apischema.typing import get_args, get_origin
from apischema.utils import Undefined, is_hashable, map_values, to_camel_case, type_name

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


U = TypeVar("U")


@dataclass(frozen=True)
class FieldParameter:
    name: str
    type: AnyType
    default: Any


def field_parameters(resolver: Resolver) -> Sequence[FieldParameter]:
    return [
        FieldParameter(p.name, resolver.types[p.name], p.default)
        for p in resolver.parameters
        if resolver.types[p.name] not in INFO_TYPES
    ]


@dataclass(frozen=True)
class ObjectField:
    name: str
    type: AnyType
    alias: Optional[str] = None
    conversions: Optional[Conversions] = None
    default: Any = graphql.Undefined
    deprecated: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[Collection[FieldParameter]] = None
    required: InitVar[bool] = True
    resolve: Optional[Callable] = None
    schema: InitVar[Optional[Schema]] = None
    subscribe: Optional[Callable] = None

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

    def apply_aliaser(self, aliaser: Aliaser) -> str:
        return aliaser(self.alias or self.name)


def wrap_return_type(return_type: AnyType, error_as_null: bool) -> AnyType:
    return Optional[return_type] if error_as_null else return_type


IdPredicate = Callable[[AnyType], bool]
GenericRefFactory = Callable[[AnyType], str]
UnionRefFactory = Callable[[Sequence[str]], str]


class SchemaBuilder(SchemaVisitor[Conv, Thunk[graphql.GraphQLType]]):
    def __init__(
        self,
        aliaser: Optional[Aliaser],
        is_id: Optional[IdPredicate],
        error_as_null: bool,
        generic_ref_factory: Optional[GenericRefFactory],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__()
        self.aliaser = aliaser or (lambda s: s)
        self.is_id = is_id or (lambda t: False)
        self.error_as_null = error_as_null
        self.generic_ref_factory = generic_ref_factory
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
        field_type, conversions = self._field_conversions(field, field_type)
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

    def enum(self, cls: Type[Enum]) -> Thunk[graphql.GraphQLType]:
        return self.literal([elt.value for elt in cls])

    def generic(self, cls: AnyType) -> Thunk[graphql.GraphQLType]:
        if self.generic_ref_factory is None:
            raise MissingRef
        self._ref = self.generic_ref_factory(cls)
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
            fields.append(ObjectField(field_name, field_type, default=default))
        return self.object(cls, fields)

    def new_type(self, cls: Type, super_type: AnyType) -> Thunk[graphql.GraphQLType]:
        return self.visit_with_schema(super_type, self._ref, self._schema)

    def object(
        self,
        cls: Type,
        fields: Collection[ObjectField],
        merged_fields: Mapping[str, Thunk[graphql.GraphQLType]] = None,
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

    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool
    ) -> Thunk[graphql.GraphQLType]:
        raise TypeError("TyedDict are not supported")

    def union(self, alternatives: Sequence[AnyType]) -> Thunk[graphql.GraphQLType]:
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
        # if key not in self._cache:
        #     thunk = super().visit_not_conversion(cls)
        #     if isinstance(thunk, graphql.GraphQLType):
        #         self._cache[key] = thunk
        #     else:
        #         self._cache[key] = lru_cache(maxsize=1)(thunk)
        # return self._cache[key]

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
    DeserializationSchemaVisitor[Thunk[graphql.GraphQLType]],
    SchemaBuilder[Deserialization],
):
    def _field(self, field: ObjectField) -> Tuple[str, Lazy[graphql.GraphQLInputField]]:
        field_type = self.visit_with_conversions(field.type, field.conversions)
        return field.apply_aliaser(self.aliaser), lambda: graphql.GraphQLInputField(
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
    ) -> Thunk[graphql.GraphQLType]:
        name, description = self._ref_and_desc
        name = name if name.endswith("Input") else name + "Input"
        visited_fields = dict(map(self._field, fields))
        visited_merged = map_values(self.visit, merged_fields or {})
        return lambda: graphql.GraphQLInputObjectType(
            name, lambda: merge_fields(cls, visited_fields, visited_merged), description
        )

    def _union_result(
        self, results: Iterable[Thunk[graphql.GraphQLType]]
    ) -> Thunk[graphql.GraphQLType]:
        results = list(results)  # Execute the iteration
        if len(results) == 1:
            return results[0]
        raise TypeError("Union are not supported for input")


class OutputSchemaBuilder(
    SerializationSchemaVisitor[Thunk[graphql.GraphQLType]], SchemaBuilder[Serialization]
):
    def __init__(
        self,
        aliaser: Optional[Aliaser],
        is_id: Optional[IdPredicate],
        error_as_null: bool,
        generic_ref_factory: Optional[GenericRefFactory],
        union_ref_factory: Optional[UnionRefFactory],
    ):
        super().__init__(
            aliaser, is_id, error_as_null, generic_ref_factory, union_ref_factory
        )
        self.input_builder = InputSchemaBuilder(
            aliaser, is_id, error_as_null, generic_ref_factory, union_ref_factory
        )

    def _field(self, field: ObjectField) -> Tuple[str, Lazy[graphql.GraphQLField]]:
        alias = field.apply_aliaser(self.aliaser)
        if field.resolve is not None:
            resolve = field.resolve
        else:
            resolve = lambda obj, _: getattr(obj, field.name)  # noqa: E731
        field_type = self.visit_with_conversions(field.type, field.conversions)
        args = None
        if field.parameters is not None:
            args = {}
            for param in field.parameters:
                default = graphql.Undefined
                if param.default not in {Parameter.empty, Undefined, graphql.Undefined}:
                    with suppress(Exception):
                        default = serialize(param.default)

                def arg_thunk(
                    arg_thunk=self.input_builder.visit(param.type),
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
        return alias, lambda: graphql.GraphQLField(
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
    ) -> Thunk[graphql.GraphQLType]:
        fields_and_resolvers = list(fields)
        try:
            name, description = self._ref_and_desc
        except MissingRef:
            if cls.__name__ not in ("Query", "Mutation", "Subscription"):
                raise
            name, description = cls.__name__, self._description
        for resolver_name, resolver in get_resolvers(cls).items():
            resolve = resolver_resolve(
                resolver, self.aliaser, error_as_null=self.error_as_null
            )
            resolver_field = ObjectField(
                resolver_name,
                wrap_return_type(resolver.return_type, self.error_as_null),
                conversions=resolver.conversions,
                parameters=field_parameters(resolver),
                resolve=resolve,
            )
            fields_and_resolvers.append(resolver_field)
        visited_fields = dict(map(self._field, fields_and_resolvers))
        visited_merged = map_values(self.visit, merged_fields or {})

        def field_thunk() -> graphql.GraphQLFieldMap:
            return merge_fields(
                cls,
                visited_fields,
                visited_merged,
                deref_merged_field,
            )

        interfaces = list(map(self.visit, get_interfaces(cls)))
        interface_thunk = None
        if interfaces:

            def interface_thunk() -> Collection[graphql.GraphQLInterfaceType]:
                result = {exec_thunk(i, non_null=False) for i in interfaces}
                for merged_thunk in visited_merged.values():
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


AwaitableOrNot = Union[Awaitable[T], T]
Subscribe = Callable[..., AwaitableOrNot[AsyncIterable]]

async_iterable_origins = set(map(get_origin, (AsyncIterable[Any], AsyncIterator[Any])))

_fake_type = cast(type, ...)


def graphql_schema(
    *,
    query: Iterable[Callable] = (),
    mutation: Iterable[Callable] = (),
    subscription: Iterable[Union[Subscribe, Tuple[Subscribe, Callable]]] = (),
    types: Iterable[Type] = (),
    aliaser: Aliaser = to_camel_case,
    id_types: Union[Collection[AnyType], IdPredicate] = None,
    error_as_null: bool = True,
    generic_ref_factory: GenericRefFactory = None,
    union_ref_factory: UnionRefFactory = None,
    directives: Optional[Collection[graphql.GraphQLDirective]] = None,
    description: Optional[str] = None,
    extensions: Optional[Dict[str, Any]] = None,
) -> graphql.GraphQLSchema:
    def operation_resolver(operation: Callable, *, skip_first=False) -> Resolver:
        if skip_first:
            wrapper = operation
        else:

            def wrapper(_, *args, **kwargs):
                return operation(*args, **kwargs)

        parameters = resolver_parameters(operation, skip_first=skip_first)
        return Resolver(operation, wrapper, parameters)

    query_fields: List[ObjectField] = []
    mutation_fields: List[ObjectField] = []
    subscription_fields: List[ObjectField] = []
    for operations, fields in [(query, query_fields), (mutation, mutation_fields)]:
        for operation in operations:
            resolver = operation_resolver(operation)
            fields.append(
                ObjectField(
                    operation.__name__,
                    wrap_return_type(resolver.return_type, error_as_null),
                    resolve=resolver_resolve(resolver, aliaser, error_as_null),
                    parameters=field_parameters(resolver),
                    schema=get_schema(operation),
                )
            )
    for operation in subscription:  # type: ignore
        resolve: Callable
        if isinstance(operation, tuple):
            operation, event_handler = operation
            name, schema = event_handler.__name__, get_schema(event_handler)
            try:
                resolver = operation_resolver(event_handler, skip_first=True)
            except MissingFirstParameter:
                raise TypeError(
                    "Subscription resolver must have at least one parameter"
                ) from None
            return_type = resolver.return_type
            subscribe = resolver_resolve(
                operation_resolver(operation),
                aliaser,
                error_as_null,
                serialized=False,
            )
            resolve = resolver_resolve(resolver, aliaser, error_as_null)
        else:
            name, schema = operation.__name__, get_schema(operation)
            resolver = operation_resolver(operation)
            if get_origin(resolver.return_type) not in async_iterable_origins:
                raise TypeError(
                    "Subscriptions must return an AsyncIterable/AsyncIterator"
                )
            return_type = get_args(resolver.return_type)[0]
            subscribe = resolver_resolve(
                resolver, aliaser, error_as_null, serialized=False
            )

            def resolve(_, *args, **kwargs):
                return _

        subscription_fields.append(
            ObjectField(
                name,
                wrap_return_type(return_type, error_as_null),
                parameters=field_parameters(resolver),
                resolve=resolve,
                subscribe=subscribe,
                schema=schema,
            )
        )

    is_id = id_types.__contains__ if isinstance(id_types, Collection) else id_types
    builder = OutputSchemaBuilder(
        aliaser, is_id, error_as_null, generic_ref_factory, union_ref_factory
    )

    def root_type(
        name: str, fields: Collection[ObjectField]
    ) -> Optional[graphql.GraphQLObjectType]:
        if not fields:
            return None
        return exec_thunk(builder.object(type(name, (), {}), fields), non_null=False)

    return graphql.GraphQLSchema(
        root_type("Query", query_fields),
        root_type("Mutation", mutation_fields),
        root_type("Subscription", subscription_fields),
        [exec_thunk(builder.visit(cls), non_null=False) for cls in types],
        directives,
        description,
        extensions,
    )
