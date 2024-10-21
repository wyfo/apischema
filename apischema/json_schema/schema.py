from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from itertools import chain
from typing import (
    AbstractSet,
    Any,
    Callable,
    ClassVar,
    Collection,
    Dict,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.aliases import Aliaser
from apischema.conversions import converters
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dependencies import get_dependent_required
from apischema.discriminators import (
    Discriminator,
    get_discriminated_parent,
    get_discriminator,
    get_inherited_discriminator,
    rec_subclasses,
)
from apischema.json_schema.conversions_resolver import WithConversionsResolver
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.refs import DeserializationRefsExtractor, Refs
from apischema.json_schema.refs import RefsExtractor as RefsExtractor_
from apischema.json_schema.refs import SerializationRefsExtractor
from apischema.json_schema.types import JsonSchema, JsonType, json_schema
from apischema.json_schema.versions import JsonSchemaVersion, RefFactory
from apischema.metadata.keys import DISCRIMINATOR_METADATA, SCHEMA_METADATA
from apischema.objects import AliasedStr, ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.ordering import Ordering, sort_by_order
from apischema.schemas import Schema
from apischema.schemas import get_schema as _get_schema
from apischema.schemas import merge_schema
from apischema.serialization import serialize
from apischema.serialization.serialized_methods import (
    SerializedMethod,
    get_serialized_methods,
)
from apischema.type_names import TypeNameFactory, get_type_name
from apischema.types import AnyType, UndefinedType
from apischema.typing import get_args, get_origin, is_typed_dict, is_union
from apischema.utils import (
    context_setter,
    get_origin_or_type,
    identity,
    is_hashable,
    is_union_of,
    literal_values,
)
from apischema.visitor import Unsupported


def get_schema(tp: AnyType) -> Optional[Schema]:
    from apischema import settings

    return merge_schema(settings.base_schema.type(tp), _get_schema(tp))


def get_field_schema(tp: AnyType, field: ObjectField) -> Optional[Schema]:
    from apischema import settings

    assert not field.is_aggregate
    return merge_schema(
        settings.base_schema.field(tp, field.name, field.alias), field.schema
    )


def get_method_schema(tp: AnyType, method: SerializedMethod) -> Optional[Schema]:
    from apischema import settings

    return merge_schema(
        settings.base_schema.method(tp, method.func, method.alias), method.schema
    )


def full_schema(base_schema: JsonSchema, schema: Optional[Schema]) -> JsonSchema:
    if schema is not None:
        base_schema = JsonSchema(base_schema)
        schema.merge_into(base_schema)
    return base_schema


Method = TypeVar("Method", bound=Callable)


@dataclass(frozen=True)
class Property:
    alias: AliasedStr
    name: str
    ordering: Optional[Ordering]
    required: bool
    schema: JsonSchema


class SchemaBuilder(
    ConversionsVisitor[Conv, JsonSchema],
    ObjectVisitor[JsonSchema],
    WithConversionsResolver,
):
    def __init__(
        self,
        additional_properties: bool,
        default_conversion: DefaultConversion,
        ignore_first_ref: bool,
        ref_factory: RefFactory,
        refs: Collection[str],
    ):
        super().__init__(default_conversion)
        self.additional_properties = additional_properties
        self._ignore_first_ref = ignore_first_ref
        self.ref_factory = ref_factory
        self.refs = refs

    def ref_schema(self, ref: Optional[str]) -> Optional[JsonSchema]:
        if ref not in self.refs:
            return None
        elif self._ignore_first_ref:
            self._ignore_first_ref = False
            return None
        else:
            assert isinstance(ref, str)
            return JsonSchema({"$ref": self.ref_factory(ref)})

    def discriminator_schema(
        self, discriminator: Discriminator, types: Sequence[type]
    ) -> Mapping[str, Any]:
        discriminator_schema: Dict[str, Any] = {
            "propertyName": AliasedStr(discriminator.alias)
        }
        mapping = {
            key: self.ref_factory(type_name)
            for key, tp in discriminator.get_mapping(types).items()
            for type_name in [get_type_name(tp).json_schema]
            if type_name is not None and type_name != key
        }
        if mapping:
            discriminator_schema["mapping"] = mapping
        return {"discriminator": discriminator_schema}

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> JsonSchema:
        schema = None
        discriminator: Optional[Discriminator] = None
        for annotation in reversed(annotations):
            if isinstance(annotation, TypeNameFactory):
                ref = annotation.to_type_name(tp).json_schema
                ref_schema = self.ref_schema(ref)
                if ref_schema is not None:
                    return full_schema(ref_schema, schema)
            if isinstance(annotation, Mapping):
                schema = merge_schema(annotation.get(SCHEMA_METADATA), schema)
                if DISCRIMINATOR_METADATA in annotation and is_union(get_origin(tp)):
                    discriminator = annotation[DISCRIMINATOR_METADATA]
        res = full_schema(super().annotated(tp, annotations), schema)
        return (
            json_schema(
                oneOf=res["anyOf"],
                **self.discriminator_schema(discriminator, get_args(tp)),
            )
            if discriminator is not None
            else res
        )

    def any(self) -> JsonSchema:
        return JsonSchema()

    def collection(self, cls: Type[Collection], value_type: AnyType) -> JsonSchema:
        return json_schema(
            type=JsonType.ARRAY,
            items=self.visit(value_type),
            uniqueItems=issubclass(cls, AbstractSet),
        )

    def enum(self, cls: Type[Enum]) -> JsonSchema:
        if len(cls) == 0:
            raise TypeError("Empty enum")
        return self.literal(list(cls))

    def literal(self, values: Sequence[Any]) -> JsonSchema:
        if not values:
            raise TypeError("Empty Literal")
        types = {JsonType.from_type(type(v)) for v in literal_values(values)}
        # Mypy issue
        type_: Any = types.pop() if len(types) == 1 else types
        if len(values) == 1:
            return json_schema(type=type_, const=values[0])
        else:
            return json_schema(type=type_, enum=values)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> JsonSchema:
        with context_setter(self):
            self._ignore_first_ref = True
            key = self.visit(key_type)
        if "type" not in key or key["type"] != JsonType.STRING:
            raise ValueError("Mapping types must have string-convertible keys")
        value = self.visit(value_type)
        if "pattern" in key:
            return json_schema(
                type=JsonType.OBJECT, patternProperties={key["pattern"]: value}
            )
        else:
            return json_schema(type=JsonType.OBJECT, additionalProperties=value)

    def visit_field(
        self, tp: AnyType, field: ObjectField, required: bool = True
    ) -> JsonSchema:
        assert not field.is_aggregate
        result = full_schema(
            self.visit_with_conv(field.type, self._field_conversion(field)),
            get_field_schema(tp, field) if tp is not None else field.schema,
        )
        if not required and "default" not in result:
            result = JsonSchema(result)
            with suppress(Exception):
                result["default"] = serialize(
                    field.type,
                    field.get_default(),
                    fall_back_on_any=False,
                    check_type=True,
                    conversion=field.serialization,
                )
        return result

    def _object_schema(self, cls: type, field: ObjectField) -> JsonSchema:
        assert field.is_aggregate
        with context_setter(self):
            self._ignore_first_ref = True
            object_schema = full_schema(
                self.visit_with_conv(field.type, self._field_conversion(field)),
                field.schema,
            )
        if object_schema.get("type") not in {JsonType.OBJECT, "object"}:
            field_type = "Flattened" if field.flattened else "Properties"
            raise TypeError(
                f"{field_type} field {cls.__name__}.{field.name}"
                f" must have an object type"
            )
        return object_schema

    def _properties_schema(
        self, object_schema: JsonSchema, pattern: Optional[Pattern] = None
    ):
        if "patternProperties" in object_schema:
            if pattern is not None:
                for p in (pattern, pattern.pattern):
                    if p in object_schema["patternProperties"]:
                        return object_schema["patternProperties"][p]
            elif (
                len(object_schema["patternProperties"]) == 1
                and "additionalProperties" not in object_schema
            ):
                return next(iter(object_schema["patternProperties"].values()))
        if isinstance(object_schema.get("additionalProperties"), Mapping):
            return object_schema["additionalProperties"]
        return JsonSchema()

    def properties(
        self, tp: AnyType, fields: Sequence[ObjectField]
    ) -> Sequence[Property]:
        raise NotImplementedError

    def object(self, tp: AnyType, fields: Sequence[ObjectField]) -> JsonSchema:
        cls = get_origin_or_type(tp)
        properties = sort_by_order(
            cls, self.properties(tp, fields), lambda p: p.name, lambda p: p.ordering
        )
        flattened_schemas: List[JsonSchema] = []
        pattern_properties = {}
        additional_properties: Union[bool, JsonSchema] = self.additional_properties
        for field in fields:
            if field.flattened:
                self._object_schema(cls, field)  # check the field is an object
                flattened_schemas.append(
                    full_schema(
                        self.visit_with_conv(field.type, self._field_conversion(field)),
                        field.schema,
                    )
                )
            elif field.pattern_properties is not None:
                if field.pattern_properties is ...:
                    pattern = infer_pattern(field.type, self.default_conversion)
                else:
                    assert isinstance(field.pattern_properties, Pattern)
                    pattern = field.pattern_properties
                pattern_properties[pattern] = self._properties_schema(
                    self._object_schema(cls, field), pattern
                )
            elif field.additional_properties:
                additional_properties = self._properties_schema(
                    self._object_schema(cls, field)
                )
        alias_by_names = {f.name: f.alias for f in fields}.__getitem__
        dependent_required = get_dependent_required(cls)
        result = []
        if discriminator_parent := get_discriminated_parent(cls):
            discriminator_ref = self.ref_schema(
                get_type_name(discriminator_parent).json_schema
            )
            assert discriminator_ref is not None
            result.append(discriminator_ref)
            additional_properties = True
        result.append(
            json_schema(
                type=JsonType.OBJECT,
                properties={p.alias: p.schema for p in properties},
                required=[p.alias for p in properties if p.required],
                additionalProperties=additional_properties,
                patternProperties=pattern_properties,
                dependentRequired={
                    alias_by_names(f): sorted(
                        map(alias_by_names, dependent_required[f])
                    )
                    for f in sorted(dependent_required, key=alias_by_names)
                },
            )
        )
        if flattened_schemas:
            return json_schema(
                allOf=result + flattened_schemas, unevaluatedProperties=False
            )
        elif len(result) == 1:
            return result[0]
        else:
            return json_schema(allOf=result)

    def primitive(self, cls: Type) -> JsonSchema:
        return JsonSchema(type=JsonType.from_type(cls))

    def tuple(self, types: Sequence[AnyType]) -> JsonSchema:
        return json_schema(
            type=JsonType.ARRAY,
            prefixItems=[self.visit(cls) for cls in types],
            items=False,
            minItems=len(types),
            maxItems=len(types),
        )

    def _visited_union(self, results: Sequence[JsonSchema]) -> JsonSchema:
        if len(results) == 1:
            return results[0]
        elif any(alt == {} for alt in results):
            return JsonSchema()
        elif all(alt.keys() == {"type"} for alt in results):
            types: Any = chain.from_iterable(
                (
                    [res["type"]]
                    if isinstance(res["type"], (str, JsonType))
                    else res["type"]
                )
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
                    if isinstance(types, (str, JsonType)):
                        types = [types]
                    if "null" not in types:
                        result = JsonSchema({**result, "type": [*types, "null"]})
                    return result
            else:
                raise NotImplementedError
        else:
            return json_schema(anyOf=results)

    def union(self, types: Sequence[AnyType]) -> JsonSchema:
        result = super().union(types)
        if get_inherited_discriminator(types) is not None:
            result = json_schema(oneOf=result["anyOf"])
        return result

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Conv],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> JsonSchema:
        schema = None
        if not dynamic:
            for ref_tp in self.resolve_conversion(tp):
                ref_schema = self.ref_schema(get_type_name(ref_tp).json_schema)
                if ref_schema is not None:
                    if (
                        conversion is not None
                        and is_hashable(tp)
                        and get_discriminator(tp) is not None
                    ):
                        return self.visit(Union[tuple(rec_subclasses(tp))])
                    return ref_schema
            if get_args(tp):
                schema = merge_schema(schema, get_schema(get_origin_or_type(tp)))
            schema = merge_schema(schema, get_schema(tp))
            if (
                conversion is not None
                and is_hashable(tp)
                and (discriminator := get_discriminator(tp))
            ):
                discriminator_alias = AliasedStr(discriminator.alias)
                try:
                    parent_schema = self.visit_with_conv(tp, conversion=identity)
                except Unsupported:
                    parent_schema = json_schema(type=JsonType.OBJECT)
                required = parent_schema.get("required", [])
                if discriminator_alias not in required:
                    required = required + [discriminator_alias]
                properties = parent_schema.get("properties", {})
                if discriminator_alias not in properties:
                    properties = {
                        **properties,
                        discriminator_alias: json_schema(type=JsonType.STRING),
                    }
                return full_schema(
                    JsonSchema(
                        {
                            **parent_schema,
                            "required": required,
                            "properties": properties,
                            **self.discriminator_schema(
                                discriminator, list(rec_subclasses(tp))
                            ),
                        }
                    ),
                    schema,
                )
        result = super().visit_conversion(tp, conversion, dynamic, next_conversion)
        return full_schema(result, schema)

    RefsExtractor: ClassVar[Type[RefsExtractor_]]


class DeserializationSchemaBuilder(
    SchemaBuilder[Deserialization],
    DeserializationVisitor[JsonSchema],
    DeserializationObjectVisitor[JsonSchema],
):
    RefsExtractor = DeserializationRefsExtractor

    def properties(
        self, tp: AnyType, fields: Sequence[ObjectField]
    ) -> Sequence[Property]:
        return [
            Property(
                AliasedStr(field.alias),
                field.name,
                field.ordering,
                field.required,
                self.visit_field(tp, field, field.required),
            )
            for field in fields
            if not field.is_aggregate
        ]


class SerializationSchemaBuilder(
    SchemaBuilder[Serialization],
    SerializationVisitor[JsonSchema],
    SerializationObjectVisitor[JsonSchema],
):
    RefsExtractor = SerializationRefsExtractor

    @staticmethod
    def _field_required(field: ObjectField):
        from apischema import settings

        return not field.skippable(
            settings.serialization.exclude_defaults, settings.serialization.exclude_none
        )

    def properties(
        self, tp: AnyType, fields: Sequence[ObjectField]
    ) -> Sequence[Property]:
        from apischema import settings

        return [
            Property(
                AliasedStr(field.alias),
                field.name,
                field.ordering,
                required,
                self.visit_field(tp, field, required),
            )
            for field in fields
            if not field.is_aggregate
            for required in [
                (
                    field.required
                    if is_typed_dict(get_origin_or_type(tp))
                    else not field.skippable(
                        settings.serialization.exclude_defaults,
                        settings.serialization.exclude_none,
                    )
                )
            ]
        ] + [
            Property(
                AliasedStr(serialized.alias),
                serialized.func.__name__,
                serialized.ordering,
                not is_union_of(types["return"], UndefinedType),
                full_schema(
                    self.visit_with_conv(types["return"], serialized.conversion),
                    get_method_schema(tp, serialized),
                ),
            )
            for serialized, types in get_serialized_methods(tp)
        ]


TypesWithConversion = Collection[Union[AnyType, Tuple[AnyType, AnyConversion]]]


def _default_version(
    version: Optional[JsonSchemaVersion],
    ref_factory: Optional[RefFactory],
    all_refs: Optional[bool],
) -> Tuple[JsonSchemaVersion, RefFactory, bool]:
    from apischema import settings

    if version is None:
        version = settings.json_schema_version
    if ref_factory is None:
        ref_factory = version.ref_factory
    if all_refs is None:
        all_refs = version.all_refs
    return version, ref_factory, all_refs


def _extract_refs(
    types: TypesWithConversion,
    default_conversion: DefaultConversion,
    builder: Type[SchemaBuilder],
    all_refs: bool,
) -> Mapping[str, AnyType]:
    refs: Refs = {}
    for tp in types:
        conversion = None
        if isinstance(tp, tuple):
            tp, conversion = tp
        builder.RefsExtractor(default_conversion, refs).visit_with_conv(tp, conversion)
    filtr = (lambda count: True) if all_refs else (lambda count: count > 1)
    return {ref: tp for ref, (tp, count) in refs.items() if filtr(count)}


def _refs_schema(
    builder: Type[SchemaBuilder],
    default_conversion: DefaultConversion,
    refs: Mapping[str, AnyType],
    ref_factory: RefFactory,
    additional_properties: bool,
) -> Mapping[str, JsonSchema]:
    return {
        ref: builder(
            additional_properties, default_conversion, True, ref_factory, refs
        ).visit(tp)
        for ref, tp in refs.items()
    }


def _schema(
    builder: Type[SchemaBuilder],
    tp: AnyType,
    schema: Optional[Schema],
    conversion: Optional[AnyConversion],
    default_conversion: DefaultConversion,
    version: Optional[JsonSchemaVersion],
    aliaser: Optional[Aliaser],
    ref_factory: Optional[RefFactory],
    all_refs: Optional[bool],
    with_schema: bool,
    additional_properties: Optional[bool],
) -> Mapping[str, Any]:
    from apischema import settings

    add_defs = ref_factory is None
    if aliaser is None:
        aliaser = settings.aliaser
    if additional_properties is None:
        additional_properties = settings.additional_properties
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    refs = _extract_refs([(tp, conversion)], default_conversion, builder, all_refs)
    json_schema = builder(
        additional_properties, default_conversion, False, ref_factory, refs
    ).visit_with_conv(tp, conversion)
    json_schema = full_schema(json_schema, schema)
    if add_defs and version.defs:
        defs = _refs_schema(
            builder, default_conversion, refs, ref_factory, additional_properties
        )
        if defs:
            json_schema["$defs"] = defs
    result = serialize(
        JsonSchema,
        json_schema,
        aliaser=aliaser,
        check_type=True,
        conversion=version.conversion,
        default_conversion=converters.default_serialization,
        fall_back_on_any=True,
    )
    if with_schema and version.schema is not None:
        result["$schema"] = version.schema
    return result


def deserialization_schema(
    tp: AnyType,
    *,
    additional_properties: Optional[bool] = None,
    aliaser: Optional[Aliaser] = None,
    all_refs: Optional[bool] = None,
    conversion: Optional[AnyConversion] = None,
    default_conversion: Optional[DefaultConversion] = None,
    ref_factory: Optional[RefFactory] = None,
    schema: Optional[Schema] = None,
    version: Optional[JsonSchemaVersion] = None,
    with_schema: bool = True,
) -> Mapping[str, Any]:
    from apischema import settings

    return _schema(
        DeserializationSchemaBuilder,
        tp,
        schema,
        conversion,
        default_conversion or settings.deserialization.default_conversion,
        version,
        aliaser,
        ref_factory,
        all_refs,
        with_schema,
        additional_properties,
    )


def serialization_schema(
    tp: AnyType,
    *,
    additional_properties: Optional[bool] = None,
    all_refs: Optional[bool] = None,
    aliaser: Optional[Aliaser] = None,
    conversion: Optional[AnyConversion] = None,
    default_conversion: Optional[DefaultConversion] = None,
    ref_factory: Optional[RefFactory] = None,
    schema: Optional[Schema] = None,
    version: Optional[JsonSchemaVersion] = None,
    with_schema: bool = True,
) -> Mapping[str, Any]:
    from apischema import settings

    return _schema(
        SerializationSchemaBuilder,
        tp,
        schema,
        conversion,
        default_conversion or settings.serialization.default_conversion,
        version,
        aliaser,
        ref_factory,
        all_refs,
        with_schema,
        additional_properties,
    )


def _defs_schema(
    types: TypesWithConversion,
    default_conversion: DefaultConversion,
    builder: Type[SchemaBuilder],
    ref_factory: RefFactory,
    all_refs: bool,
    additional_properties: bool,
) -> Mapping[str, JsonSchema]:
    return _refs_schema(
        builder,
        default_conversion,
        _extract_refs(types, default_conversion, builder, all_refs),
        ref_factory,
        additional_properties,
    )


def _set_missing_properties(
    schema: JsonSchema, properties: Optional[Mapping[str, JsonSchema]], key: str
) -> JsonSchema:
    if properties is None:
        return schema
    missing = {name: prop for name, prop in properties.items() if prop.get(key, False)}
    schema.setdefault("properties", {}).update(missing)
    return schema


def compare_schemas(write: Any, read: Any) -> Any:
    if isinstance(write, Mapping):
        if not isinstance(read, Mapping):
            raise ValueError
        merged: Dict[str, Any] = {}
        for key in write.keys() | read.keys():
            if key in write and key in read:
                if key == "properties":
                    merged[key] = {}
                    for prop in write[key].keys() | read[key].keys():
                        if prop in write[key] and prop in read[key]:
                            merged[key][prop] = compare_schemas(
                                write[key][prop], read[key][prop]
                            )
                        elif prop in write[key]:
                            merged[key][prop] = {**write[key][prop], "writeOnly": True}
                        else:
                            merged[key][prop] = {**read[key][prop], "readOnly": True}
                elif key in {
                    "required",
                    "dependentRequired",
                    "additionalProperties",
                    "patternProperties",
                }:
                    merged[key] = write[key]
                else:
                    merged[key] = compare_schemas(write[key], read[key])
            else:
                merged[key] = write.get(key, read.get(key))
        return merged
    elif isinstance(read, Sequence) and not isinstance(read, str):
        if not isinstance(read, Sequence) or len(write) != len(read):
            raise ValueError
        return [compare_schemas(write[i], read[i]) for i in range(len(write))]
    else:
        if not write == read:
            raise ValueError
        return write


def definitions_schema(
    *,
    deserialization: TypesWithConversion = (),
    serialization: TypesWithConversion = (),
    default_deserialization: Optional[DefaultConversion] = None,
    default_serialization: Optional[DefaultConversion] = None,
    aliaser: Optional[Aliaser] = None,
    version: Optional[JsonSchemaVersion] = None,
    ref_factory: Optional[RefFactory] = None,
    all_refs: Optional[bool] = None,
    additional_properties: Optional[bool] = None,
) -> Mapping[str, Mapping[str, Any]]:
    from apischema import settings

    if additional_properties is None:
        additional_properties = settings.additional_properties
    if aliaser is None:
        aliaser = settings.aliaser
    if default_deserialization is None:
        default_deserialization = settings.deserialization.default_conversion
    if default_serialization is None:
        default_serialization = settings.serialization.default_conversion
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    deserialization_schemas = _defs_schema(
        deserialization,
        default_deserialization,
        DeserializationSchemaBuilder,
        ref_factory,
        all_refs,
        additional_properties,
    )
    serialization_schemas = _defs_schema(
        serialization,
        default_serialization,
        SerializationSchemaBuilder,
        ref_factory,
        all_refs,
        additional_properties,
    )
    schemas = {}
    for ref in deserialization_schemas.keys() | serialization_schemas.keys():
        if ref in deserialization_schemas and ref in serialization_schemas:
            try:
                schemas[ref] = compare_schemas(
                    deserialization_schemas[ref], serialization_schemas[ref]
                )
            except ValueError:
                raise TypeError(
                    f"Reference {ref} has different schemas"
                    f" for deserialization and serialization"
                )
        else:
            schemas[ref] = deserialization_schemas.get(
                ref, serialization_schemas.get(ref)
            )
    return {
        ref: serialize(
            JsonSchema,
            schema,
            aliaser=aliaser,
            fall_back_on_any=True,
            check_type=True,
            conversion=version.conversion,
            default_conversion=converters.default_serialization,
        )
        for ref, schema in schemas.items()
    }
