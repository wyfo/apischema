from contextlib import ExitStack, contextmanager
from enum import Enum
from itertools import chain
from typing import (
    AbstractSet,
    Any,
    Collection,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Type,
    Union,
)

from apischema import settings
from apischema.aliases import Aliaser
from apischema.conversions.conversions import Conversions
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dataclasses import replace
from apischema.dependencies import get_dependent_required
from apischema.json_schema.constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
)
from apischema.json_schema.generation.conversions_resolver import (
    WithConversionsResolver,
)
from apischema.json_schema.generation.refs import (
    DeserializationRefsExtractor,
    Refs,
    RefsExtractor as RefsExtractor_,
    SerializationRefsExtractor,
)
from apischema.json_schema.patterns import infer_pattern
from apischema.json_schema.schemas import Schema, get_schema, merge_schema
from apischema.json_schema.types import JsonSchema, JsonType, json_schema
from apischema.json_schema.versions import JsonSchemaVersion, RefFactory
from apischema.metadata.keys import SCHEMA_METADATA
from apischema.objects import ObjectField
from apischema.objects.visitor import (
    DeserializationObjectVisitor,
    ObjectVisitor,
    SerializationObjectVisitor,
)
from apischema.serialization import serialize
from apischema.serialization.serialized_methods import get_serialized_methods
from apischema.type_names import TypeNameFactory, get_type_name
from apischema.types import AnyType, OrderedDict, UndefinedType
from apischema.typing import get_args, get_origin, is_annotated, is_new_type
from apischema.utils import is_union_of, sort_by_annotations_position

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore


constraint_by_type = {
    int: NumberConstraints,
    float: NumberConstraints,
    str: StringConstraints,
}


def full_schema(base_schema: JsonSchema, schema: Optional[Schema]) -> JsonSchema:
    if schema is not None:
        base_schema = JsonSchema(base_schema)
        schema.merge_into(base_schema)
    return base_schema


class SchemaBuilder(
    ConversionsVisitor[Conv, JsonSchema],
    ObjectVisitor[JsonSchema],
    WithConversionsResolver,
):
    def __init__(
        self,
        ref_factory: RefFactory,
        refs: Collection[str],
        ignore_first_ref: bool,
        additional_properties: bool,
    ):
        super().__init__()
        self.ref_factory = ref_factory
        self.refs = refs
        self.additional_properties = additional_properties
        self._ignore_first_ref = ignore_first_ref
        self._schema: Optional[Schema] = None

    @contextmanager
    def _tmp_ignore_first_ref(self):
        ignore_first_ref = self._ignore_first_ref
        self._ignore_first_ref = True
        try:
            yield
        finally:
            self._ignore_first_ref = ignore_first_ref

    def _check_constraints(self, expected: Type[Constraints]):
        if self._schema is not None and self._schema.constraints is not None:
            if not isinstance(self._schema.constraints, expected):
                raise TypeError(
                    f"Bad constraints: expected {expected.__name__}"
                    f" found {type(self._schema.constraints).__name__}"
                )

    @contextmanager
    def _replace_schema(self, schema: Optional[Schema]):
        schema_save = self._schema
        self._schema = schema
        try:
            yield
        finally:
            self._schema = schema_save

    def ref_schema(self, ref: Optional[str]) -> Optional[JsonSchema]:
        if ref not in self.refs:
            return None
        elif self._ignore_first_ref:
            self._ignore_first_ref = False
            return None
        else:
            assert isinstance(ref, str)
            return full_schema(
                JsonSchema({"$ref": self.ref_factory(ref)}), self._schema
            )

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> JsonSchema:
        with ExitStack() as exit_stack:
            for annotation in reversed(annotations):
                if isinstance(annotation, TypeNameFactory):
                    ref = annotation.to_type_name(tp).json_schema
                    ref_schema = self.ref_schema(ref)
                    if ref_schema is not None:
                        return ref_schema
                if isinstance(annotation, Mapping) and SCHEMA_METADATA in annotation:
                    exit_stack.enter_context(
                        self._replace_schema(
                            merge_schema(annotation[SCHEMA_METADATA], self._schema)
                        )
                    )
            return self.visit(tp)
        raise NotImplementedError  # for mypy

    def any(self) -> JsonSchema:
        return JsonSchema()

    def collection(self, cls: Type[Iterable], value_type: AnyType) -> JsonSchema:
        self._check_constraints(ArrayConstraints)
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
        types = {
            JsonType.from_type(type(v.value if isinstance(v, Enum) else v))
            for v in values
        }
        # Mypy issue
        type_: Any = types.pop() if len(types) == 1 else types
        if len(values) == 1:
            return json_schema(type=type_, const=values[0])
        else:
            return json_schema(type=type_, enum=values)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> JsonSchema:
        self._check_constraints(ObjectConstraints)
        with self._tmp_ignore_first_ref():
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

    def visit_field(self, field: ObjectField) -> JsonSchema:
        schema = field.schema
        if (
            field.annotations is not None
            and not field.required
            and field.annotations.default is ...
        ):
            try:
                default = serialize(
                    field.get_default(), conversions=field.serialization
                )
            except Exception:
                pass
            else:
                annotations = replace(field.annotations, default=default)
                assert field.schema is not None
                schema = replace(field.schema, annotations=annotations)
        with self._replace_conversions(self._field_conversion(field)):
            with self._replace_schema(schema):
                return self.visit(field.type)

    def _properties_schema(self, field: ObjectField) -> JsonSchema:
        assert field.pattern_properties is not None or field.additional_properties
        with self._tmp_ignore_first_ref():
            props_schema = self.visit_field(field)
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

    def _check_merged_schema(self, cls: Type, field: ObjectField):
        assert field.merged
        with self._tmp_ignore_first_ref():
            if self.visit_field(field).get("type") not in {JsonType.OBJECT, "object"}:
                raise TypeError(
                    f"Merged field {cls.__name__}.{field.name} must have an object type"
                )

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> JsonSchema:
        self._check_constraints(ObjectConstraints)
        merged_schemas: List[JsonSchema] = []
        pattern_properties = {}
        additional_properties: Union[bool, JsonSchema] = self.additional_properties
        properties = {}
        required = []
        for field in fields:
            if field.merged:
                self._check_merged_schema(cls, field)
                merged_schemas.append(self.visit_field(field))
            elif field.pattern_properties is not None:
                if field.pattern_properties is ...:
                    pattern = infer_pattern(field.type)
                else:
                    assert isinstance(field.pattern_properties, Pattern)
                    pattern = field.pattern_properties
                pattern_properties[pattern] = self._properties_schema(field)
            elif field.additional_properties:
                additional_properties = self._properties_schema(field)
            else:
                properties[field.alias] = self.visit_field(field)
                if field.required:
                    required.append(field.alias)
        alias_by_names = {f.name: f.alias for f in fields}.__getitem__
        dependent_required = get_dependent_required(cls)
        result = json_schema(
            type=JsonType.OBJECT,
            properties=properties,
            required=required,
            additionalProperties=additional_properties,
            patternProperties=pattern_properties,
            dependentRequired=OrderedDict(
                (alias_by_names(f), sorted(map(alias_by_names, dependent_required[f])))
                for f in sorted(dependent_required, key=alias_by_names)
            ),
        )
        if merged_schemas:
            result = json_schema(
                type=JsonType.OBJECT,
                allOf=[result, *merged_schemas],
                unevaluatedProperties=False,
            )
        return result

    def primitive(self, cls: Type) -> JsonSchema:
        if cls in constraint_by_type:
            self._check_constraints(constraint_by_type[cls])
        return JsonSchema(type=JsonType.from_type(cls))

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

    def _union_result(self, results: Iterable[JsonSchema]) -> JsonSchema:
        results = list(results)
        if len(results) == 1:
            return results[0]
        elif any(alt == {} for alt in results):
            return JsonSchema()
        elif all(alt.keys() == {"type"} for alt in results):
            types: Any = chain.from_iterable(
                [res["type"]]
                if isinstance(res["type"], (str, JsonType))
                else res["type"]
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

    def union(self, alternatives: Sequence[AnyType]) -> JsonSchema:
        return super().union([alt for alt in alternatives if alt is not UndefinedType])

    def visit_conversion(
        self, tp: AnyType, conversion: Optional[Conv], dynamic: bool
    ) -> JsonSchema:
        if dynamic:
            with self._replace_schema(None):
                return super().visit_conversion(tp, conversion, dynamic)
        for ref_tp in self.resolve_conversions(tp):
            ref_schema = self.ref_schema(get_type_name(ref_tp).json_schema)
            if ref_schema is not None:
                return ref_schema
        schema = merge_schema(get_schema(tp), self._schema)
        if is_new_type(tp) or is_annotated(tp):
            with self._replace_schema(schema):
                return super().visit_conversion(tp, conversion, dynamic)
        if get_args(tp):
            schema = merge_schema(get_schema(get_origin(tp)), schema)
        with self._replace_schema(None):
            return full_schema(
                super().visit_conversion(tp, conversion, dynamic), schema
            )

    RefsExtractor: Type[RefsExtractor_]


class DeserializationSchemaBuilder(
    SchemaBuilder[Deserialization],
    DeserializationVisitor[JsonSchema],
    DeserializationObjectVisitor[JsonSchema],
):
    RefsExtractor = DeserializationRefsExtractor


class SerializationSchemaBuilder(
    SchemaBuilder[Serialization],
    SerializationVisitor[JsonSchema],
    SerializationObjectVisitor[JsonSchema],
):
    RefsExtractor = SerializationRefsExtractor

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> JsonSchema:
        result = super().object(cls, fields)
        name_by_aliases = {f.alias: f.name for f in fields}
        properties = {}
        required = []
        for alias, (serialized, types) in get_serialized_methods(
            self._generic or cls
        ).items():
            ret = types["return"]
            with self._replace_schema(serialized.schema):
                properties[alias] = json_schema(
                    **self.visit_with_conversions(ret, serialized.conversions)
                )
            if not is_union_of(ret, UndefinedType):
                required.append(alias)
            name_by_aliases[alias] = serialized.func.__name__
        if "allOf" not in result:
            to_update = result
        else:
            to_update = result["allOf"][0]
        if required:
            required.extend(to_update.get("required", ()))
            to_update["required"] = sorted(required)
        if properties:
            properties.update(to_update.get("properties", {}))
            props = sort_by_annotations_position(
                cls, properties, lambda p: name_by_aliases[p]
            )
            to_update["properties"] = {p: properties[p] for p in props}
        return result


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


def _extract_refs(
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
    refs: Mapping[str, AnyType],
    ref_factory: RefFactory,
    additional_properties: bool,
) -> Mapping[str, JsonSchema]:
    return {
        ref: builder(ref_factory, refs, True, additional_properties).visit(cls)
        for ref, cls in refs.items()
    }


def _schema(
    builder: Type[SchemaBuilder],
    tp: AnyType,
    schema: Optional[Schema],
    conversions: Optional[Conversions],
    version: Optional[JsonSchemaVersion],
    aliaser: Optional[Aliaser],
    ref_factory: Optional[RefFactory],
    all_refs: Optional[bool],
    with_schema: bool,
    addtional_properties: Optional[bool],
) -> Mapping[str, Any]:
    add_defs = ref_factory is None
    if aliaser is None:
        aliaser = settings.aliaser()
    if addtional_properties is None:
        addtional_properties = settings.additional_properties
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    refs = _extract_refs([(tp, conversions)], builder, all_refs)
    visitor = builder(ref_factory, refs, False, addtional_properties)
    with visitor._replace_schema(schema):
        json_schema = visitor.visit_with_conversions(tp, conversions)
    if add_defs:
        defs = _refs_schema(builder, refs, ref_factory, addtional_properties)
        if defs:
            json_schema["$defs"] = defs
    result = serialize(json_schema, conversions=version.conversion, aliaser=aliaser)
    if with_schema and version.schema is not None:
        result["$schema"] = version.schema
    return result


def deserialization_schema(
    tp: AnyType,
    *,
    schema: Schema = None,
    conversions: Conversions = None,
    version: JsonSchemaVersion = None,
    aliaser: Aliaser = None,
    ref_factory: RefFactory = None,
    all_refs: bool = None,
    with_schema: bool = True,
    additional_properties: bool = None,
) -> Mapping[str, Any]:
    return _schema(
        DeserializationSchemaBuilder,
        tp,
        schema,
        conversions,
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
    schema: Schema = None,
    conversions: Conversions = None,
    version: JsonSchemaVersion = None,
    aliaser: Aliaser = None,
    ref_factory: RefFactory = None,
    all_refs: bool = None,
    with_schema: bool = True,
    additional_properties: bool = None,
) -> Mapping[str, Any]:
    return _schema(
        SerializationSchemaBuilder,
        tp,
        schema,
        conversions,
        version,
        aliaser,
        ref_factory,
        all_refs,
        with_schema,
        additional_properties,
    )


def _defs_schema(
    types: TypesWithConversions,
    builder: Type[SchemaBuilder],
    ref_factory: RefFactory,
    all_refs: bool,
    additional_properties: bool,
) -> Mapping[str, JsonSchema]:
    return _refs_schema(
        builder,
        _extract_refs(types, builder, all_refs),
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
    deserialization: TypesWithConversions = (),
    serialization: TypesWithConversions = (),
    aliaser: Aliaser = None,
    version: JsonSchemaVersion = None,
    ref_factory: Optional[RefFactory] = None,
    all_refs: bool = None,
    addtional_properties: bool = None,
) -> Mapping[str, Mapping[str, Any]]:
    if addtional_properties is None:
        addtional_properties = settings.additional_properties
    if aliaser is None:
        aliaser = settings.aliaser()
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    deserialization_schemas = _defs_schema(
        deserialization,
        DeserializationSchemaBuilder,
        ref_factory,
        all_refs,
        addtional_properties,
    )
    serialization_schemas = _defs_schema(
        serialization,
        SerializationSchemaBuilder,
        ref_factory,
        all_refs,
        addtional_properties,
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
        ref: serialize(schema, conversions=version.conversion, aliaser=aliaser)
        for ref, schema in schemas.items()
    }
