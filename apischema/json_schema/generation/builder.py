from contextlib import contextmanager
from dataclasses import Field, replace
from enum import Enum
from functools import wraps
from itertools import chain
from typing import (  # type: ignore
    AbstractSet,
    Any,
    Callable,
    Collection,
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

from apischema import settings
from apischema.aliases import Aliaser
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import Conv
from apischema.dataclass_utils import (
    get_alias,
    get_default,
    has_default,
    is_dataclass,
    is_required,
)
from apischema.json_schema.constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
)
from apischema.json_schema.generation.refs import Refs, RefsExtractor
from apischema.json_schema.generation.visitor import (
    DeserializationSchemaVisitor,
    SchemaVisitor,
    SerializationSchemaVisitor,
)
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.refs import get_ref, schema_ref
from apischema.json_schema.schema import Schema, get_schema, merge_schema
from apischema.json_schema.types import JsonSchema, JsonType, json_schema
from apischema.json_schema.versions import JsonSchemaVersion, RefFactory
from apischema.metadata.keys import (
    MERGED_METADATA,
    PROPERTIES_METADATA,
    SCHEMA_METADATA,
    check_metadata,
)
from apischema.resolvers import Resolver
from apischema.serialization import get_serialized_resolvers, serialize
from apischema.types import AnyType
from apischema.utils import is_hashable, map_values

constraint_by_type = {
    int: NumberConstraints,
    float: NumberConstraints,
    str: StringConstraints,
}


Method = TypeVar("Method", bound=Callable[..., JsonSchema])


def with_schema(method: Method) -> Method:
    @wraps(method)
    def wrapper(self: "SchemaBuilder", *args, **kwargs):
        if self._schema is None:
            return method(self, *args, **kwargs)
        elif self._schema.override:
            return JsonSchema(**self._schema.as_dict())
        else:
            return JsonSchema(method(self, *args, **kwargs), **self._schema.as_dict())

    return cast(Method, wrapper)


class SchemaBuilder(SchemaVisitor[Conv, JsonSchema]):
    def __init__(
        self,
        aliaser: Aliaser,
        ref_factory: RefFactory,
        refs: Collection[str],
        ignore_first_ref: bool,
    ):
        super().__init__()
        self.ref_factory = ref_factory
        self.refs = refs
        self.ignore_first_ref = ignore_first_ref
        self.aliaser = aliaser
        self._schema: Optional[Schema] = None

    def _check_constraints(self, expected: Type[Constraints]):
        if self._schema is not None and self._schema.constraints is not None:
            if not isinstance(self._schema.constraints, expected):
                raise TypeError(
                    f"Bad constraints: expected {expected.__name__}"
                    f" found {type(self._schema.constraints).__name__}"
                )

    def _merge_schema(self, schema: Optional[Schema]):
        self._schema = merge_schema(schema, self._schema)

    @with_schema
    def _ref_schema(self, ref: str) -> JsonSchema:
        return JsonSchema({"$ref": self.ref_factory(ref)})

    def annotated(self, cls: AnyType, annotations: Sequence[Any]) -> JsonSchema:
        for annotation in reversed(annotations):
            if isinstance(annotation, schema_ref):
                annotation.check_type(cls)
                if annotation.ref in self.refs:
                    if self.ignore_first_ref:
                        self.ignore_first_ref = False
                    else:
                        assert isinstance(annotation.ref, str)
                        return self._ref_schema(annotation.ref)
                ref = annotation.ref
                if not isinstance(ref, str):
                    raise ValueError("Annotated schema_ref can only be str")
            if isinstance(annotation, Schema):
                self._merge_schema(annotation)
        return self.visit_with_schema(cls, self._schema)

    @with_schema
    def any(self) -> JsonSchema:
        return JsonSchema()

    @with_schema
    def collection(self, cls: Type[Iterable], value_type: AnyType) -> JsonSchema:
        self._check_constraints(ArrayConstraints)
        return json_schema(
            type=JsonType.ARRAY,
            items=self.visit(value_type),
            uniqueItems=issubclass(cls, AbstractSet),
        )

    def _visit_field_(self, field: Field, field_type: AnyType):
        if SCHEMA_METADATA in field.metadata:
            schema: Schema = field.metadata[SCHEMA_METADATA]
            if schema.annotations is not None and schema.annotations is ...:
                if not has_default(field):
                    raise TypeError("Invalid ... without field default")
                try:
                    _, conversions = self._field_conversions(field, field_type)
                    default = serialize(get_default(field), conversions=conversions)
                except Exception:
                    pass
                else:
                    annotations = replace(schema.annotations, default=default)
                    schema = replace(schema, annotations=annotations)
            return self.visit_with_schema(field_type, schema)
        else:
            return self.visit(field_type)

    def _properties_schema(self, field: Field, field_type: AnyType) -> JsonSchema:
        with self._without_ref():
            props_schema = self._visit_field(field, field_type)
        if not props_schema.get("type") == JsonType.OBJECT:
            raise TypeError("properties field must have an 'object' type")
        if "patternProperties" in props_schema:
            if (
                len(props_schema["patternProperties"]) != 1
                or "additionalProperties" in props_schema
            ):  # don't try to merge the schemas
                pass
            else:
                return next(iter(props_schema["patternProperties"].values()))
        elif "additionalProperties" in props_schema:
            if isinstance(props_schema["additionalProperties"], JsonSchema):
                return props_schema["additionalProperties"]
            else:  # there is maybe only properties
                pass
        return JsonSchema()

    @with_schema
    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> JsonSchema:
        assert is_dataclass(cls)
        self._check_constraints(ObjectConstraints)
        properties = {}
        required: List[str] = []
        merged_schemas = []
        pattern_properties = {}
        additional_properties: Union[bool, JsonSchema] = settings.additional_properties
        for field in self._dataclass_fields(fields, init_vars):
            metadata = check_metadata(field)
            field_type = types[field.name]
            if MERGED_METADATA in metadata:
                merged_schemas.append(self._visit_field(field, field_type))
            elif PROPERTIES_METADATA in metadata:
                pattern = metadata[PROPERTIES_METADATA]
                properties_schema = self._properties_schema(field, field_type)
                if pattern is None:
                    additional_properties = properties_schema
                elif pattern is ...:
                    pattern_properties[infer_pattern(field_type)] = properties_schema
                else:
                    pattern_properties[pattern] = properties_schema
            else:
                alias = self.aliaser(get_alias(field))
                properties[alias] = json_schema(
                    readOnly=not field.init,
                    writeOnly=field in init_vars,
                    **self._visit_field(field, field_type),
                )
                if is_required(field):
                    required.append(alias)
        for name, resolver in self._resolvers(cls).items():
            with self._replace_conversions(resolver.conversions):
                properties[self.aliaser(name)] = json_schema(
                    readOnly=True,
                    **self.visit_with_schema(resolver.return_type, resolver.schema),
                )
        dep_req = self._dependent_required(cls)
        result = json_schema(
            type=JsonType.OBJECT,
            properties=properties,
            required=required,
            additionalProperties=additional_properties,
            patternProperties=pattern_properties,
            dependentRequired={
                alias: sorted(self.aliaser(get_alias(f)) for f in dep_req[req])
                for alias, req in sorted(
                    [(self.aliaser(get_alias(req)), req) for req in dep_req],
                    key=lambda t: t[0],
                )
            },
        )
        if merged_schemas:
            result = json_schema(
                type=JsonType.OBJECT,
                allOf=[result, *merged_schemas],
                unevaluatedProperties=False,
            )
        return result

    def enum(self, cls: Type[Enum]) -> JsonSchema:
        if len(cls) == 0:
            raise TypeError("Empty enum")
        return self.literal(list(cls))

    @with_schema
    def literal(self, values: Sequence[Any]) -> JsonSchema:
        if not values:
            raise TypeError("Empty Literal")
        types = sorted(
            set(
                JsonType.from_type(type(v.value if isinstance(v, Enum) else v))
                for v in values
            )
        )
        # Mypy issue
        type_: Any = types[0] if len(types) == 1 else types
        if len(values) == 1:
            return json_schema(type=type_, const=values[0])
        else:
            return json_schema(type=type_, enum=values)

    @with_schema
    def mapping(
        self,
        cls: Type[Mapping],
        key_type: AnyType,
        value_type: AnyType,
    ) -> JsonSchema:
        self._check_constraints(ObjectConstraints)
        with self._without_ref():
            key = self.visit(key_type)
        if key["type"] != JsonType.STRING:
            raise ValueError("Mapping types must string-convertible key")
        value = self.visit(value_type)
        if "pattern" in key:
            return json_schema(
                type=JsonType.OBJECT, patternProperties={key["pattern"]: value}
            )
        else:
            return json_schema(type=JsonType.OBJECT, additionalProperties=value)

    @with_schema
    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> JsonSchema:
        self._check_constraints(ObjectConstraints)
        return json_schema(
            type=JsonType.OBJECT,
            properties={
                self.aliaser(key): self.visit(key) for key, cls in types.items()
            },
            required=sorted(types.keys() - defaults.keys()),
            additionalProperties=settings.additional_properties,
        )

    def new_type(self, cls: Type, super_type: AnyType) -> JsonSchema:
        return self.visit_with_schema(super_type, self._schema)

    @with_schema
    def primitive(self, cls: Type) -> JsonSchema:
        if cls in constraint_by_type:
            self._check_constraints(constraint_by_type[cls])
        return JsonSchema(type=JsonType.from_type(cls))

    def subprimitive(self, cls: Type, superclass: Type) -> JsonSchema:
        return self.primitive(superclass)

    @with_schema
    def tuple(self, types: Sequence[AnyType]) -> JsonSchema:
        self._check_constraints(ArrayConstraints)
        if self._schema is not None and self._schema.constraints is not None:
            assert isinstance(self._schema.constraints, ArrayConstraints)
            if (
                self._schema.constraints.max_items is not None
                or self._schema.constraints.min_items is not None
            ):
                raise TypeError("Tuple cannot have min_items/max_items constraints")
        return json_schema(
            type=JsonType.ARRAY,
            items=[self.visit(cls) for cls in types],
            minItems=len(types),
            maxItems=len(types),
        )

    @with_schema
    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool
    ) -> JsonSchema:
        self._check_constraints(ObjectConstraints)
        return json_schema(
            type=JsonType.OBJECT,
            properties=map_values(self.visit, keys),
            required=list(keys) if total else [],
        )

    @with_schema
    def _union_result(self, results: Iterable[JsonSchema]) -> JsonSchema:
        results = list(results)
        if len(results) == 1:
            return results[0]
        elif all(alt.keys() == {"type"} for alt in results):
            types = chain.from_iterable(
                [res["type"]] if isinstance(res["type"], JsonType) else res["type"]
                for res in results
            )
            return json_schema(type=list(types))
        elif (
            len(results) == 2
            and all("type" in res for res in results)
            and {"type": "null"} in results
        ):
            for result in results:
                if result != {"type": "null"}:
                    types = result["type"]
                    if isinstance(types, str):
                        types = [types]  # type: ignore
                    if "null" not in types:
                        result = JsonSchema({**result, "type": [*types, "null"]})
                    return result
            else:
                raise NotImplementedError()
        else:
            return json_schema(anyOf=results)

    def visit_with_schema(self, cls: AnyType, schema: Optional[Schema]) -> JsonSchema:
        schema_save = self._schema
        if is_hashable(cls) and not self.is_extra_conversions(cls):
            self._schema = schema
            ref = get_ref(cls)
            if ref in self.refs:
                if self.ignore_first_ref:
                    self.ignore_first_ref = False
                else:
                    assert isinstance(ref, str)
                    return self._ref_schema(ref)
            cls_schema = get_schema(cls)
            if cls_schema is not None and not cls_schema.override:
                # Constraints are merged in case of not conversions
                cls_schema = replace(cls_schema, constraints=None)
            self._merge_schema(cls_schema)
        else:
            self._schema = None
        try:
            return super().visit(cls)
        finally:
            self._schema = schema_save

    def visit_not_conversion(self, cls: AnyType) -> JsonSchema:
        if self._schema is None or not self._schema.override:
            self._merge_schema(get_schema(cls))
        return super().visit_not_conversion(cls)

    def visit(self, cls: AnyType) -> JsonSchema:
        return self.visit_with_schema(cls, None)

    @contextmanager
    def _without_ref(self):
        refs_save = self.refs
        self.refs = ()
        try:
            yield
        finally:
            self.refs = refs_save

    RefsExtractor: Type["RefsExtractor"]


class DeserializationSchemaBuilder(DeserializationSchemaVisitor, SchemaBuilder):
    class RefsExtractor(DeserializationSchemaVisitor, RefsExtractor):  # type: ignore
        pass


class SerializationSchemaBuilder(SerializationSchemaVisitor, SchemaBuilder):
    class RefsExtractor(SerializationSchemaVisitor, RefsExtractor):  # type: ignore
        pass

    def _resolvers(self, cls: Type) -> Mapping[str, Resolver]:
        return get_serialized_resolvers(cls)


TypesWithConversions = Collection[Union[AnyType, Tuple[AnyType, Conversions]]]


def _default_version(
    version: Optional[JsonSchemaVersion],
    ref_factory: Optional[RefFactory],
    all_refs: Optional[bool],
) -> Tuple[JsonSchemaVersion, RefFactory, bool]:
    if version is None:
        version = settings.json_schema_version
    if ref_factory is None:
        ref_factory = version.ref_factory
    if all_refs is None:
        all_refs = version.all_refs
    return version, ref_factory, all_refs


def _export_refs(
    types: TypesWithConversions, builder: Type[SchemaBuilder], all_refs: bool
) -> Mapping[str, AnyType]:
    refs: Refs = {}
    for cls in types:
        conversions = None
        if isinstance(cls, tuple):
            cls, conversions = cls
        builder.RefsExtractor(refs).visit_with_conversions(cls, conversions)
    filtr = (lambda count: True) if all_refs else (lambda count: count > 1)
    return {ref: cls for ref, (cls, count) in refs.items() if filtr(count)}


def _refs_schema(
    builder: Type[SchemaBuilder],
    aliaser: Aliaser,
    refs: Mapping[str, AnyType],
    ref_factory: RefFactory,
) -> Mapping[str, JsonSchema]:
    return {
        ref: builder(aliaser, ref_factory, refs, True).visit(cls)
        for ref, cls in refs.items()
    }


def _schema(
    builder: Type[SchemaBuilder],
    cls: AnyType,
    schema: Optional[Schema],
    conversions: Optional[Conversions],
    version: Optional[JsonSchemaVersion],
    aliaser: Optional[Aliaser],
    ref_factory: Optional[RefFactory],
    all_refs: Optional[bool],
    with_schema: bool,
) -> Mapping[str, Any]:
    add_defs = ref_factory is None
    if ref_factory is not None and all_refs is None:
        all_refs = True
    if aliaser is None:
        aliaser = settings.aliaser()
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    refs = _export_refs([(cls, conversions)], builder, all_refs)
    visitor = builder(aliaser, ref_factory, refs, False)
    with visitor._replace_conversions(conversions):
        json_schema = visitor.visit_with_schema(cls, schema)
    if add_defs:
        defs = _refs_schema(builder, aliaser, refs, ref_factory)
        if defs:
            json_schema["$defs"] = defs
    result = serialize(json_schema, conversions=version.conversions)
    if with_schema and version.schema is not None:
        result["$schema"] = version.schema
    return result


def deserialization_schema(
    cls: AnyType,
    *,
    schema: Schema = None,
    conversions: Conversions = None,
    version: JsonSchemaVersion = None,
    aliaser: Aliaser = None,
    ref_factory: RefFactory = None,
    all_refs: bool = None,
    with_schema: bool = True,
) -> Mapping[str, Any]:
    return _schema(
        DeserializationSchemaBuilder,
        cls,
        schema,
        conversions,
        version,
        aliaser,
        ref_factory,
        all_refs,
        with_schema,
    )


def serialization_schema(
    cls: AnyType,
    *,
    schema: Schema = None,
    conversions: Conversions = None,
    version: JsonSchemaVersion = None,
    aliaser: Aliaser = None,
    ref_factory: RefFactory = None,
    all_refs: bool = None,
    with_schema: bool = True,
) -> Mapping[str, Any]:
    return _schema(
        SerializationSchemaBuilder,
        cls,
        schema,
        conversions,
        version,
        aliaser,
        ref_factory,
        all_refs,
        with_schema,
    )


def _defs_schema(
    types: TypesWithConversions,
    builder: Type[SchemaBuilder],
    aliaser: Aliaser,
    ref_factory: RefFactory,
    all_refs: bool,
) -> Mapping[str, JsonSchema]:
    return _refs_schema(
        builder, aliaser, _export_refs(types, builder, all_refs), ref_factory
    )


def _set_missing_properties(
    schema: JsonSchema, properties: Optional[Mapping[str, JsonSchema]], key: str
) -> JsonSchema:
    if properties is None:
        return schema
    missing = {name: prop for name, prop in properties.items() if prop.get(key, False)}
    schema.setdefault("properties", {}).update(missing)
    return schema


def definitions_schema(
    *,
    deserialization: TypesWithConversions = (),
    serialization: TypesWithConversions = (),
    aliaser: Aliaser = None,
    version: JsonSchemaVersion = None,
    ref_factory: Optional[RefFactory] = None,
    all_refs: bool = None,
) -> Mapping[str, Mapping[str, Any]]:
    if aliaser is None:
        aliaser = settings.aliaser()
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    deserialization_schemas = _defs_schema(
        deserialization, DeserializationSchemaBuilder, aliaser, ref_factory, all_refs
    )
    serialization_schemas = _defs_schema(
        serialization, SerializationSchemaBuilder, aliaser, ref_factory, all_refs
    )
    for duplicate in deserialization_schemas.keys() & serialization_schemas.keys():
        d_schema = deserialization_schemas[duplicate]
        s_schema = serialization_schemas[duplicate]
        _set_missing_properties(s_schema, d_schema.get("properties"), "writeOnly")
        _set_missing_properties(d_schema, s_schema.get("properties"), "readOnly")
        if "required" in d_schema and "required" in s_schema:
            s_schema["required"] = d_schema["required"]
        if d_schema != s_schema:
            raise TypeError(
                f"Reference {duplicate} has different schemas"
                f" for deserialization and serialization"
            )
    return {
        ref: serialize(schema, conversions=version.conversions)
        for ref, schema in chain(
            deserialization_schemas.items(), serialization_schemas.items()
        )
    }
