from collections import defaultdict
from contextlib import contextmanager
from enum import Enum
from itertools import chain
from typing import (  # type: ignore
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
    Set,
    Tuple,
    Type,
    Union,
    cast,
)

from apischema import settings
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import Conv
from apischema.dataclasses import is_dataclass, replace
from apischema.dataclasses.cache import Field, FieldKind
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
from apischema.json_schema.schema import (
    Schema,
    get_schema,
    merge_schema,
    serialize_schema,
)
from apischema.json_schema.types import JsonSchema, JsonType, json_schema
from apischema.json_schema.versions import JsonSchemaVersion, RefFactory
from apischema.metadata.keys import is_aggregate_field
from apischema.serialization import serialize
from apischema.types import AnyType
from apischema.utils import get_default, is_hashable

constraint_by_type = {
    int: NumberConstraints,
    float: NumberConstraints,
    str: StringConstraints,
}


def check_constraints(schema: Optional[Schema], expected: Type[Constraints]):
    if schema is not None and schema.constraints is not None:
        if not isinstance(schema.constraints, expected):
            raise TypeError(
                f"Bad constraints: expected {expected.__name__}"
                f" found {type(schema.constraints).__name__}"
            )


def check_no_constraints(schema: Optional[Schema], type_):
    if schema is not None and schema.constraints is not None:
        raise TypeError(f"{type} cannot have constraints")


def _with_schema(schema: Optional[Schema], json_schema: JsonSchema) -> JsonSchema:
    if schema is None:
        return json_schema
    elif schema.override:
        return JsonSchema(**serialize_schema(schema))
    else:
        return JsonSchema(json_schema, **serialize_schema(schema))


class SchemaBuilder(SchemaVisitor[Conv, Optional[Schema], JsonSchema]):
    def __init__(
        self,
        conversions: Optional[Conversions],
        ref_factory: RefFactory,
        refs: Collection[str],
        ignore_first_ref: bool,
    ):
        super().__init__(conversions)
        self.ref_factory = ref_factory
        self.refs = refs
        self.ignore_first_ref = ignore_first_ref

    def _ref_schema(self, ref: str, schema: Optional[Schema]) -> JsonSchema:
        return _with_schema(schema, JsonSchema({"$ref": self.ref_factory(ref)}))

    def _annotated(
        self, cls: AnyType, annotations: Sequence[Any], schema: Optional[Schema]
    ) -> JsonSchema:
        for annotation in reversed(annotations):
            if isinstance(annotation, schema_ref):
                annotation.check_type(cls)
                if annotation.ref in self.refs:
                    if self.ignore_first_ref:
                        self.ignore_first_ref = False
                    else:
                        assert isinstance(annotation.ref, str)
                        return self._ref_schema(annotation.ref, schema)
                ref = annotation.ref
                if not isinstance(ref, str):
                    raise ValueError("Annotated schema_ref can only be str")
            if isinstance(annotation, Schema):
                schema = merge_schema(annotation, schema)
        return self.visit(cls, schema)

    def any(self, schema: Optional[Schema]) -> JsonSchema:
        check_no_constraints(schema, "Any")
        return _with_schema(schema, JsonSchema())

    def collection(
        self, cls: Type[Iterable], value_type: AnyType, schema: Optional[Schema]
    ) -> JsonSchema:
        check_constraints(schema, ArrayConstraints)
        return _with_schema(
            schema,
            json_schema(
                type=JsonType.ARRAY,
                items=self.visit(value_type),
                uniqueItems=issubclass(cls, AbstractSet),
            ),
        )

    @staticmethod
    def _override_arg(cls: AnyType, schema: Optional[Schema]) -> Optional[Schema]:
        return merge_schema(get_schema(cls), schema)

    def _field_schema(self, field: Field) -> Schema:
        annotations = field.annotations
        if annotations is not None and annotations.default is ...:
            if not field.default:
                raise TypeError("Invalid ... without field default")
            try:
                default = serialize(get_default(field.base_field))
            except Exception:
                pass
            else:
                annotations = replace(annotations, default=default)
        return Schema(annotations, field.constraints)

    def _visit_field(self, field: Field) -> JsonSchema:
        result = self._field_visit(field, self._field_schema(field))
        if not is_aggregate_field(field.base_field):
            result = json_schema(
                readOnly=field.kind == FieldKind.NO_INIT,
                writeOnly=field.kind == FieldKind.INIT,
                **result,
            )
        return result

    def _properties_schema(self, field: Field) -> JsonSchema:
        props_schema = JsonSchema()
        with self._without_ref():
            props_schema = self._visit_field(field)
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

    _required: bool

    def dataclass(self, cls: Type, schema: Optional[Schema]) -> JsonSchema:
        assert is_dataclass(cls)
        check_constraints(schema, ObjectConstraints)
        properties = {}
        required: List[str] = []
        (
            fields,
            merged_fields,
            pattern_fields,
            additional_field,
        ) = self._dataclass_fields(cls)
        dependent: Dict[str, Set[str]] = defaultdict(set)
        for field in fields:
            properties[field.alias] = self._visit_field(field)
            if not field.default:
                required.append(field.alias)
            for req in self._required_by(field):
                dependent[req].add(field.alias)
        dependent_required = {
            field: sorted(dependent[field]) for field in sorted(dependent)
        }

        merged_schemas = [self._visit_field(field) for _, field in merged_fields]
        pattern_properties = {
            cast(Pattern, pattern)
            if pattern is not ...
            else infer_pattern(field): self._properties_schema(field)
            for pattern, field in pattern_fields
        }
        additional_properties: Union[bool, JsonSchema]
        if additional_field:
            additional_properties = self._properties_schema(additional_field)
        else:
            additional_properties = settings.additional_properties
        result = json_schema(
            type=JsonType.OBJECT,
            properties=properties,
            required=required,
            additionalProperties=additional_properties,
            patternProperties=pattern_properties,
            dependentRequired=dependent_required,
        )
        if merged_schemas:
            result = json_schema(
                type=JsonType.OBJECT,
                allOf=[result, *merged_schemas],
                unevaluatedProperties=False,
            )
        return _with_schema(schema, result)

    def enum(self, cls: Type[Enum], schema: Optional[Schema]) -> JsonSchema:
        check_no_constraints(schema, "Enum")
        if len(cls) == 0:
            raise TypeError("Empty enum")
        return self.literal(list(cls), schema)

    def literal(self, values: Sequence[Any], schema: Optional[Schema]) -> JsonSchema:
        check_no_constraints(schema, "Literal")
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
        return _with_schema(
            schema,
            json_schema(type_=type_, enum=values)
            if len(values) != 1
            else json_schema(type=type_, const=values[0]),
        )

    def mapping(
        self,
        cls: Type[Mapping],
        key_type: AnyType,
        value_type: AnyType,
        schema: Optional[Schema],
    ) -> JsonSchema:
        check_constraints(schema, ObjectConstraints)
        with self._without_ref():
            key = self.visit(key_type)
        if key["type"] != JsonType.STRING:
            raise ValueError("Mapping types must string-convertible key")
        value = self.visit(value_type)
        return _with_schema(
            schema,
            json_schema(type=JsonType.OBJECT, patternProperties={key["pattern"]: value})
            if "pattern" in key
            else json_schema(type=JsonType.OBJECT, additionalProperties=value),
        )

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
        schema: Optional[Schema],
    ) -> JsonSchema:
        check_constraints(schema, ObjectConstraints)
        return _with_schema(
            schema,
            json_schema(
                type=JsonType.OBJECT,
                properties={key: self.visit(key) for key, cls in types.items()},
                required=sorted(types.keys() - defaults.keys()),
                additionalProperties=settings.additional_properties,
            ),
        )

    def new_type(
        self, cls: AnyType, super_type: AnyType, schema: Optional[Schema]
    ) -> JsonSchema:
        return self.visit(super_type, schema)

    def primitive(self, cls: Type, schema: Optional[Schema]) -> JsonSchema:
        if cls in constraint_by_type:
            check_constraints(schema, constraint_by_type[cls])
        return _with_schema(schema, JsonSchema(type=JsonType.from_type(cls)))

    def subprimitive(
        self, cls: Type, superclass: Type, schema: Optional[Schema]
    ) -> JsonSchema:
        return self.primitive(superclass, schema)

    def tuple(self, types: Sequence[AnyType], schema: Optional[Schema]) -> JsonSchema:
        check_constraints(schema, ArrayConstraints)
        if schema is not None and schema.constraints is not None:
            assert isinstance(schema.constraints, ArrayConstraints)
            if (
                schema.constraints.max_items is not None
                or schema.constraints.min_items is not None
            ):
                raise TypeError("Tuple cannot have min_items/max_items constraints")
        return _with_schema(
            schema,
            json_schema(
                type=JsonType.ARRAY,
                items=[self.visit(cls) for cls in types],
                minItems=len(types),
                maxItems=len(types),
            ),
        )

    def typed_dict(
        self,
        cls: Type,
        keys: Mapping[str, AnyType],
        total: bool,
        schema: Optional[Schema],
    ) -> JsonSchema:
        check_constraints(schema, ObjectConstraints)
        return _with_schema(
            schema,
            json_schema(
                type=JsonType.OBJECT,
                properties={key: self.visit(cls) for key, cls in keys.items()},
                required=list(keys) if total else [],
            ),
        )

    def _union_arg(self, cls: AnyType, arg: Optional[Schema]) -> Optional[Schema]:
        return None

    def _union_result(
        self, results: Sequence[JsonSchema], schema: Optional[Schema]
    ) -> JsonSchema:
        if len(results) == 1:
            result = results[0]
        elif all(alt.keys() == {"type"} for alt in results):
            types = chain.from_iterable(
                [res["type"]] if isinstance(res["type"], JsonType) else res["type"]
                for res in results
            )
            result = json_schema(type=list(types))
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
                    break
            else:
                raise NotImplementedError()
        else:
            result = json_schema(anyOf=results)
        return _with_schema(schema, result)

    def visit(self, cls: AnyType, schema: Optional[Schema] = None) -> JsonSchema:
        if self._is_conversion(cls):
            return self.visit_not_builtin(cls, merge_schema(get_schema(cls), schema))
        if is_hashable(cls):
            ref = get_ref(cls)
            if ref in self.refs:
                if self.ignore_first_ref:
                    self.ignore_first_ref = False
                else:
                    assert isinstance(ref, str)
                    return self._ref_schema(ref, schema)
            schema = merge_schema(get_schema(cls), schema)
        return super().visit(cls, schema)

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
        builder.RefsExtractor(conversions, refs).visit(cls)
    filtr = (lambda count: True) if all_refs else (lambda count: count > 1)
    return {ref: cls for ref, (cls, count) in refs.items() if filtr(count)}


def _refs_schema(
    builder: Type[SchemaBuilder], refs: Mapping[str, AnyType], ref_factory: RefFactory
) -> Mapping[str, JsonSchema]:
    return {
        ref: builder(None, ref_factory, refs, True).visit(cls)
        for ref, cls in refs.items()
    }


def _schema(
    builder: Type[SchemaBuilder],
    cls: AnyType,
    schema: Optional[Schema],
    conversions: Optional[Conversions],
    version: Optional[JsonSchemaVersion],
    ref_factory: Optional[RefFactory],
    all_refs: Optional[bool],
    with_schema: bool,
) -> Mapping[str, Any]:
    add_defs = ref_factory is None
    if ref_factory is not None and all_refs is None:
        all_refs = True
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    refs = _export_refs([(cls, conversions)], builder, all_refs)
    json_schema = builder(conversions, ref_factory, refs, False).visit(cls, schema)
    if add_defs:
        defs = _refs_schema(builder, refs, ref_factory)
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
        ref_factory,
        all_refs,
        with_schema,
    )


def _defs_schema(
    types: TypesWithConversions,
    builder: Type[SchemaBuilder],
    ref_factory: RefFactory,
    all_refs: bool,
) -> Mapping[str, JsonSchema]:
    return _refs_schema(builder, _export_refs(types, builder, all_refs), ref_factory)


def _set_missing_properties(
    schema: JsonSchema, properties: Optional[Mapping[str, JsonSchema]], key: str,
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
    version: JsonSchemaVersion = None,
    ref_factory: Optional[RefFactory] = None,
    all_refs: bool = None,
) -> Mapping[str, Mapping[str, Any]]:
    version, ref_factory, all_refs = _default_version(version, ref_factory, all_refs)
    deserialization_schemas = _defs_schema(
        deserialization, DeserializationSchemaBuilder, ref_factory, all_refs
    )
    serialization_schemas = _defs_schema(
        serialization, SerializationSchemaBuilder, ref_factory, all_refs
    )
    for duplicate in deserialization_schemas.keys() & serialization_schemas.keys():
        d_schema = deserialization_schemas[duplicate]
        s_schema = serialization_schemas[duplicate]
        _set_missing_properties(
            s_schema, d_schema.get("properties"), "writeOnly",
        )
        _set_missing_properties(
            d_schema, s_schema.get("properties"), "readOnly",
        )
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
