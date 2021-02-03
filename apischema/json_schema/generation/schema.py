from contextlib import contextmanager
from dataclasses import Field, dataclass
from enum import Enum
from functools import wraps
from itertools import chain
from typing import (  # type: ignore
    AbstractSet,
    Any,
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

from apischema import settings
from apischema.aliases import Aliaser
from apischema.conversions import identity
from apischema.conversions.conversions import Conversions
from apischema.conversions.utils import Converter
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    DeserializationVisitor,
    SerializationVisitor,
)
from apischema.dataclass_utils import (
    get_alias,
    get_default,
    get_field_conversions,
    get_fields,
    get_requirements,
    has_default,
    is_dataclass,
    is_required,
)
from apischema.dataclasses import replace
from apischema.dependent_required import DependentRequired
from apischema.json_schema.constraints import (
    ArrayConstraints,
    Constraints,
    NumberConstraints,
    ObjectConstraints,
    StringConstraints,
)
from apischema.json_schema.generation.refs import Refs, RefsExtractor
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
from apischema.serialization import serialize
from apischema.serialization.serialized_methods import get_serialized_methods
from apischema.skip import filter_skipped
from apischema.tagged_unions import TAGS_ATTR
from apischema.types import AnyType, OrderedDict
from apischema.typing import get_origin
from apischema.utils import UndefinedType, is_union_of, sort_by_annotations_position

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
        schema = self._schema.as_dict()
        if not self._schema.override:
            schema = {**method(self, *args, **kwargs), **schema}
        return JsonSchema(schema)

    return cast(Method, wrapper)


@dataclass(frozen=True)
class ObjectField:
    name: str
    alias: str
    required: bool
    schema: JsonSchema


class SchemaBuilder(ConversionsVisitor[Conv, JsonSchema]):
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
        self.aliaser = aliaser
        self._ignore_first_ref = ignore_first_ref
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

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> JsonSchema:
        for annotation in reversed(annotations):
            if isinstance(annotation, schema_ref):
                annotation.check_type(tp)
                if annotation.ref in self.refs:
                    if self._ignore_first_ref:
                        self._ignore_first_ref = False
                    else:
                        assert isinstance(annotation.ref, str)
                        return self._ref_schema(annotation.ref)
                ref = annotation.ref
                if not isinstance(ref, str):
                    raise ValueError("Annotated schema_ref can only be str")
            if isinstance(annotation, Mapping) and SCHEMA_METADATA in annotation:
                self._merge_schema(annotation[SCHEMA_METADATA])
        return self.visit_with_schema(tp, self._schema)

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

    def visit_field(self, field: Field, field_type: AnyType):
        conversions = get_field_conversions(field, self.operation)
        converter: Converter = identity
        schema: Optional[Schema] = None
        if SCHEMA_METADATA in field.metadata:
            schema = cast(Schema, field.metadata[SCHEMA_METADATA])
            if schema.annotations is not None and schema.annotations is ...:
                if not has_default(field):
                    raise TypeError("Invalid ... without field default")
                try:
                    default = serialize(
                        converter(get_default(field)), conversions=conversions
                    )
                except Exception:
                    pass
                else:
                    annotations = replace(schema.annotations, default=default)
                    schema = replace(schema, annotations=annotations)
        with self._replace_conversions(conversions):
            return self.visit_with_schema(field_type, schema)

    def _properties_schema(self, field: Field, field_type: AnyType) -> JsonSchema:
        with self._without_ref():
            props_schema = self.visit_field(field, field_type)
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

    def _check_merged_schema(self, cls: Type, field: Field, field_type: AnyType):
        ignore_first_ref = self._ignore_first_ref
        self._ignore_first_ref = True
        try:
            if self.visit_field(field, field_type).get("type") not in {
                JsonType.OBJECT,
                "object",
            }:
                raise TypeError(
                    f"Merged field {cls.__name__}.{field.name}"
                    f" must have an object type"
                )
        finally:
            self._ignore_first_ref = ignore_first_ref

    def _update_properties(
        self, cls: Type, properties: Dict[str, JsonSchema], required: List[str]
    ):
        pass

    def _properties(
        self, cls: Type, fields: Collection[ObjectField]
    ) -> Tuple[Mapping[str, JsonSchema], Sequence[str]]:
        properties, required = {}, []
        for field in fields:
            alias = field.alias or self.aliaser(field.name)
            properties[alias] = field.schema
            if field.required and alias not in required:
                required.append(alias)
        return properties, required

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
        merged_schemas: List[JsonSchema] = []
        pattern_properties = {}
        additional_properties: Union[bool, JsonSchema] = settings.additional_properties
        object_fields: List[ObjectField] = []
        for field in get_fields(fields, init_vars, self.operation):
            metadata = check_metadata(field)
            field_type = types[field.name]
            if MERGED_METADATA in metadata:
                self._check_merged_schema(cls, field, field_type)
                merged_schemas.append(self.visit_field(field, field_type))
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
                field_schema = json_schema(
                    readOnly=not field.init,
                    writeOnly=field in init_vars,
                    **self.visit_field(field, field_type),
                )
                object_field = ObjectField(
                    field.name, alias, is_required(field), field_schema
                )
                object_fields.append(object_field)
        properties, required = self._properties(cls, object_fields)
        dependent_required = {
            self.aliaser(get_alias(field)): sorted(
                self.aliaser(get_alias(req)) for req in required_by
            )
            for field, required_by in get_requirements(
                cls, DependentRequired.requiring, self.operation
            ).items()
        }
        if hasattr(cls, TAGS_ATTR):
            return json_schema(
                type=JsonType.OBJECT,
                oneOf=[
                    json_schema(properties={prop: value})
                    for prop, value in properties.items()
                ],
            )
        result = json_schema(
            type=JsonType.OBJECT,
            properties=properties,
            required=required,
            additionalProperties=additional_properties,
            patternProperties=pattern_properties,
            dependentRequired=OrderedDict(
                (f, dependent_required[f]) for f in sorted(dependent_required)
            ),
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

    def generic(self, tp: AnyType) -> JsonSchema:
        self._merge_schema(get_schema(get_origin(tp)))
        return super().generic(tp)

    @with_schema
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
        properties = {self.aliaser(key): self.visit(key) for key, cls in types.items()}
        required = [attr for attr in types if attr not in defaults]
        self._update_properties(cls, properties, required)
        return json_schema(
            type=JsonType.OBJECT,
            properties=properties,
            required=required,
            additionalProperties=settings.additional_properties,
        )

    def new_type(self, tp: Type, super_type: AnyType) -> JsonSchema:
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
            properties={key: self.visit(tp) for key, tp in keys.items()},
            required=list(keys) if total else [],
        )

    def _union_result(self, results: Iterable[JsonSchema]) -> JsonSchema:
        results = list(results)
        if len(results) == 1:
            return results[0]
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

    @with_schema
    def union(self, alternatives: Sequence[AnyType]) -> JsonSchema:
        return self._union_result(
            map(self.visit, filter_skipped(alternatives, schema_only=True))
        )

    def visit_with_schema(self, tp: AnyType, schema: Optional[Schema]) -> JsonSchema:
        schema_save = self._schema
        dynamic = self._apply_dynamic_conversions(tp)
        tp, self._schema = (dynamic, None) if dynamic is not None else (tp, schema)
        ref = get_ref(tp)
        if ref in self.refs:
            if self._ignore_first_ref:
                self._ignore_first_ref = False
            else:
                assert isinstance(ref, str)
                return self._ref_schema(ref)
        self._merge_schema(get_schema(tp))
        try:
            return super().visit(tp)
        finally:
            self._schema = schema_save

    def visit(self, tp: AnyType) -> JsonSchema:
        return self.visit_with_schema(tp, None)

    @contextmanager
    def _without_ref(self):
        refs_save = self.refs
        self.refs = ()
        try:
            yield
        finally:
            self.refs = refs_save

    RefsExtractor: Type["RefsExtractor"]


class DeserializationSchemaBuilder(DeserializationVisitor, SchemaBuilder):
    class RefsExtractor(DeserializationVisitor, RefsExtractor):  # type: ignore
        pass

    visit_conversion = with_schema(DeserializationVisitor.visit_conversion)  # type: ignore # noqa: E501


class SerializationSchemaBuilder(SerializationVisitor, SchemaBuilder):
    class RefsExtractor(SerializationVisitor, RefsExtractor):  # type: ignore
        pass

    def _properties(
        self, cls: Type, fields: Collection[ObjectField]
    ) -> Tuple[Mapping[str, JsonSchema], Sequence[str]]:
        all_fields = list(fields)
        for name, (serialized, types) in get_serialized_methods(
            self._generic or cls
        ).items():
            ret = types["return"]
            with self._replace_conversions(serialized.conversions):
                schema = json_schema(
                    readOnly=True, **self.visit_with_schema(ret, serialized.schema)
                )
            required = not is_union_of(ret, UndefinedType)
            all_fields.append(
                ObjectField(serialized.func.__name__, name, required, schema)
            )
        all_fields = sort_by_annotations_position(cls, all_fields, lambda f: f.name)
        return super()._properties(cls, all_fields)

    visit_conversion = with_schema(SerializationVisitor.visit_conversion)  # type: ignore # noqa: E501


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
    tp: AnyType,
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
    refs = _extract_refs([(tp, conversions)], builder, all_refs)
    visitor = builder(aliaser, ref_factory, refs, False)
    with visitor._replace_conversions(conversions):
        json_schema = visitor.visit_with_schema(tp, schema)
    if add_defs:
        defs = _refs_schema(builder, aliaser, refs, ref_factory)
        if defs:
            json_schema["$defs"] = defs
    result = serialize(json_schema, conversions=version.conversion)
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
    )


def _defs_schema(
    types: TypesWithConversions,
    builder: Type[SchemaBuilder],
    aliaser: Aliaser,
    ref_factory: RefFactory,
    all_refs: bool,
) -> Mapping[str, JsonSchema]:
    return _refs_schema(
        builder, aliaser, _extract_refs(types, builder, all_refs), ref_factory
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
        ref: serialize(schema, conversions=version.conversion)
        for ref, schema in chain(
            deserialization_schemas.items(), serialization_schemas.items()
        )
    }
