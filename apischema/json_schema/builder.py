from dataclasses import is_dataclass, replace
from enum import Enum
from itertools import chain
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
)

from apischema.conversion import Converter, InputVisitorMixin, OutputVisitorMixin
from apischema.data import to_data
from apischema.dataclasses import (
    Field,
    FieldCache,
    FieldKind,
    get_input_fields,
    get_output_fields,
)
from apischema.fields import NoDefault, get_default, get_fields_set, mark_set_fields
from apischema.ignore import Ignored
from apischema.json_schema.types import JSONSchema, JSONType
from apischema.schema import Constraint, Schema
from apischema.schema.annotations import get_annotations
from apischema.schema.constraints import (
    ArrayConstraint,
    NumberConstraint,
    ObjectConstraint,
    StringConstraint,
    get_constraint,
)
from apischema.utils import NO_DEFAULT, as_dict
from apischema.visitor import Visitor

constraint_by_type = {
    int: NumberConstraint,
    float: NumberConstraint,
    str: StringConstraint,
}


class ReadWriteOnly(Constraint):
    pass


def check_constraint(schema: Schema, expected: Type[Constraint]):
    if schema.constraint is not None:
        if not isinstance(schema.constraint, expected):
            if not isinstance(schema.constraint, ReadWriteOnly):
                raise TypeError(
                    f"Bad constraint: expected {expected.__name__}"
                    f" found {type(schema.constraint).__name__}"
                )


def _remove_none(obj: Optional[Any]) -> Iterator[Tuple[str, Any]]:
    if obj is None:
        return
    for k, v in as_dict(obj).items():
        filtered = {"items", "additional_properties"}
        if v is not None and v is not NO_DEFAULT and k not in filtered:
            yield k, v


def _to_dict(schema: Schema) -> Mapping[str, Any]:
    return dict(
        chain(_remove_none(schema.annotations), _remove_none(schema.constraint))
    )


def _merge_constraints(
    c1: Optional[Constraint], c2: Optional[Constraint]
) -> Optional[Constraint]:
    if c1 is None:
        return c2
    if c2 is None:
        return c1
    if isinstance(c1, ReadWriteOnly):
        return type(c2)(**{**as_dict(c1), **as_dict(c2)})
    elif Constraint != type(c1) != type(c2) != Constraint:
        raise TypeError(
            f"Incompatibles constraints {type(c1).__name__}" f" and {type(c2).__name__}"
        )
    return c1


def _override(schema: Schema, cls: Type) -> Schema:
    return Schema(
        schema.annotations or get_annotations(cls),
        _merge_constraints(schema.constraint, get_constraint(cls)),
    )


def _field_schema(field: Field) -> Schema:
    annotations = field.annotations
    if annotations is not None and annotations.default is ...:
        try:
            default = to_data(get_default(field.base_field))
        except NoDefault:
            raise TypeError("Invalid ... without field default")
        annotations = replace(annotations, default=default)
    return Schema(annotations, field.constraint)


def _extract_properties_schema(json_schema: JSONSchema) -> JSONSchema:
    if json_schema.pattern_properties is not None:
        if (
            len(json_schema.pattern_properties) >= 1
            or json_schema.additional_properties
        ):  # don't try to merge the schemas and return
            return JSONSchema()
        return next(iter(json_schema.pattern_properties.values()))
    if json_schema.additional_properties:
        if isinstance(json_schema.additional_properties, JSONSchema):
            return json_schema.additional_properties
        else:
            return JSONSchema()
    raise TypeError("properties field must have an 'object' schema")


class SchemaBuilder(Visitor[Schema, JSONSchema]):
    def __init__(self, ref_factory: Optional[Callable[[Type], str]]):
        super().__init__()
        self.ref_factory = ref_factory or self._missing_ref_factory
        self.schemas: Set[Type] = set()

    @staticmethod
    def _missing_ref_factory(cls: Type) -> str:
        raise TypeError("reference factory is needed to handle" " recursive types")

    def primitive(self, cls: Type, schema: Schema) -> JSONSchema:
        if cls in constraint_by_type:
            check_constraint(schema, constraint_by_type[cls])
        return JSONSchema(type=JSONType.from_type(cls), **_to_dict(schema))

    def union(self, alternatives: Sequence[Type], schema: Schema) -> JSONSchema:
        any_of = []
        for cls in alternatives:
            try:
                any_of.append(self.visit(cls, schema))
            except Ignored:
                pass
        if len(any_of) == 1:
            return any_of[0]
        else:
            return JSONSchema(any_of=any_of)

    def iterable(
        self, cls: Type[Iterable], value_type: Type, schema: Schema
    ) -> JSONSchema:
        check_constraint(schema, ArrayConstraint)
        if isinstance(schema.items_, Sequence):
            raise TypeError("Iterable items schema cannot be a list of schema")
        return JSONSchema(
            type=JSONType.ARRAY,
            items=self.visit(value_type, schema.items_),
            **_to_dict(schema),
        )

    def mapping(
        self, cls: Type[Mapping], key_type: Type, value_type: Type, schema: Schema
    ) -> JSONSchema:
        check_constraint(schema, ObjectConstraint)
        key = self.visit(key_type, Schema())
        value = self.visit(value_type, schema.additional_properties)
        properties: Dict[str, Any] = {}
        if key.pattern is not None:
            properties["pattern_properties"] = {key.pattern: value}
        else:
            properties["additional_properties"] = value
        return JSONSchema(  # type: ignore
            type=JSONType.OBJECT, **properties, **_to_dict(schema),
        )

    def typed_dict(
        self, cls: Type, keys: Mapping[str, Type], total: bool, schema: Schema
    ) -> JSONSchema:
        if cls in self.schemas:
            return JSONSchema(ref=self.ref_factory(cls))
        check_constraint(schema, ObjectConstraint)
        if schema.additional_properties:
            raise TypeError("additional properties are not handled" " for TypedDict")
        sorted_keys = sorted(keys)
        return JSONSchema(
            type=JSONType.OBJECT,
            properties={key: self.visit(keys[key], Schema()) for key in sorted_keys},
            required=sorted_keys if total else [],
            additional_properties=True,
            **_to_dict(schema),
        )

    def tuple(self, types: Sequence[Type], schema: Schema) -> JSONSchema:
        check_constraint(schema, ArrayConstraint)
        if schema.constraint is not None:
            assert isinstance(schema.constraint, ArrayConstraint)
            if (
                schema.constraint.max_items is not None
                or schema.constraint.min_items is not None
            ):
                raise TypeError("Tuple cannot have min_items/max_items" " constraint")
        if isinstance(schema.items_, Sequence):
            if len(schema.items_) != len(types):
                raise TypeError(
                    "Tuple items schema list must have the same" " length than tuple"
                )
        items = []
        for i, cls in enumerate(types):
            if isinstance(schema.items_, Sequence):
                elt_schema = schema.items_[i]
            else:
                elt_schema = schema.items_
            items.append(self.visit(cls, elt_schema))
        return JSONSchema(
            type=JSONType.ARRAY,
            items=items,
            min_items=len(types),
            max_items=len(types),
            **_to_dict(schema),
        )

    def literal(self, values: Sequence[Any], schema: Schema) -> JSONSchema:
        if not values:
            raise TypeError("empty Literal")
        if schema.constraint is not None:
            raise TypeError("Literal cannot have constraint")
        types = sorted(
            set(
                JSONType.from_type(type(v.value if isinstance(v, Enum) else v))
                for v in values
            )
        )
        # Mypy issue
        type_: Any = types[0] if len(types) == 1 else types
        if len(values) == 1:
            return JSONSchema(type=type_, const=values[0], **_to_dict(schema),)
        else:
            return JSONSchema(type=type_, enum=values, **_to_dict(schema),)

    def _dataclass_fields(self, cls: Type) -> FieldCache:
        raise NotImplementedError()

    def _field_visit(self, field: Field) -> JSONSchema:
        raise NotImplementedError()

    def dataclass(self, cls: Type, schema: Schema) -> JSONSchema:
        assert is_dataclass(cls)
        if cls in self.schemas:
            return JSONSchema(ref=self.ref_factory(cls))
        self.schemas.add(cls)
        check_constraint(schema, ObjectConstraint)
        schema_ = _override(schema, cls)
        properties = {}
        required: List[str] = []
        fields, pattern_fields, additional_field = self._dataclass_fields(cls)
        for field in fields:
            properties[field.alias] = self._field_visit(field)
            if not field.default:
                required.append(field.alias)
        pattern_properties: Dict[Pattern, JSONSchema] = {}
        for pattern, field in pattern_fields:
            field_schema = self._field_visit(field)
            pattern_properties[pattern] = _extract_properties_schema(field_schema)
        additional_properties: Optional[Union[bool, "JSONSchema"]] = False
        if additional_field:
            field_schema = self._field_visit(additional_field)
            additional_properties = _extract_properties_schema(field_schema)
        kwargs: Dict[str, Any] = {}
        if properties:
            kwargs["properties"] = properties
        if required:
            kwargs["required"] = required
        # get_fields_set(additional_properties) means that additional_properties
        # is not {} and not True
        if additional_properties is False or get_fields_set(additional_properties):
            kwargs["additional_properties"] = additional_properties
        if pattern_properties:
            kwargs["pattern_properties"] = pattern_properties
        return JSONSchema(  # type: ignore
            type=JSONType.OBJECT, **kwargs, **_to_dict(schema_),
        )

    def enum(self, cls: Type[Enum], schema: Schema) -> JSONSchema:
        if schema.constraint is not None:
            raise TypeError("enum cannot have constraint")
        if len(cls) == 0:
            raise TypeError("Empty enum")
        return self.literal(list(cls), _override(schema, cls))

    def new_type(self, cls: Type, super_type: Type, schema: Schema) -> JSONSchema:
        return self.visit(super_type, _override(schema, cls))

    def any(self, schema: Schema) -> JSONSchema:
        if schema.constraint is not None:
            raise TypeError("Any type cannot have constraint")
        return JSONSchema()

    def annotated(
        self, cls: Type, annotations: Sequence[Any], schema: Schema
    ) -> JSONSchema:
        schema_ = schema
        if Ignored in annotations:
            raise Ignored
        for annotation in annotations:
            if isinstance(annotation, Schema):
                schema_ = Schema(
                    schema.annotations or annotation.annotations,
                    _merge_constraints(schema.constraint, annotation.constraint),
                )
                break
        return self.visit(cls, schema_)


class InputSchemaBuilder(InputVisitorMixin[Schema, JSONSchema], SchemaBuilder):
    def __init__(
        self, ref_factory: Optional[Callable[[Type], str]], additional_properties: bool
    ):
        SchemaBuilder.__init__(self, ref_factory)
        self.additional_properties = additional_properties

    def _custom(
        self, cls: Type, custom: Dict[Type, Converter], schema: Schema
    ) -> JSONSchema:
        return self.union(list(custom), _override(schema, cls))

    _dataclass_fields = staticmethod(get_input_fields)  # type: ignore

    def _field_visit(self, field: Field) -> JSONSchema:
        schema = _field_schema(field)
        if field.kind == FieldKind.INIT:
            if schema.constraint is None:
                schema.constraint = ReadWriteOnly(write_only=True)
            else:
                if schema.constraint.read_only:
                    raise TypeError("InitVar cannot be read-only")
                schema.constraint = replace(schema.constraint, write_only=True)
        return self.visit(field.input_type, schema)

    def dataclass(self, cls: Type, schema: Schema) -> JSONSchema:
        json_schema = super().dataclass(cls, schema)
        if json_schema.additional_properties is False:
            # TODO document that `dataclasses.replace` don't keep fields set
            return mark_set_fields(
                replace(json_schema, additional_properties=self.additional_properties),
                *get_fields_set(json_schema),
                overwrite=True,
            )
        return json_schema


def build_input_schema(
    cls: Type,
    *,
    ref_factory: Callable[[Type], str] = None,
    additional_properties: bool = False,
    schema: Schema = None,
) -> JSONSchema:
    builder = InputSchemaBuilder(ref_factory, additional_properties)
    return builder.visit(cls, schema or Schema())


class OutputSchemaBuilder(OutputVisitorMixin[Schema, JSONSchema], SchemaBuilder):
    def __init__(
        self,
        conversions: Mapping[Type, Type],
        ref_factory: Optional[Callable[[Type], str]],
    ):
        SchemaBuilder.__init__(self, ref_factory)
        OutputVisitorMixin.__init__(self, conversions)

    def _custom(
        self, cls: Type, custom: Tuple[Type, Converter], schema: Schema
    ) -> JSONSchema:
        return self.visit(custom[0], _override(schema, cls))

    _dataclass_fields = staticmethod(get_output_fields)  # type: ignore

    def _field_visit(self, field: Field) -> JSONSchema:
        schema = _field_schema(field)
        if field.kind == FieldKind.NO_INIT:
            if schema.constraint is None:
                schema.constraint = ReadWriteOnly(read_only=True)
            else:
                if schema.constraint.write_only:
                    raise TypeError("not init field cannot be write-only")
                schema.constraint = replace(schema.constraint, read_only=True)
        return self.visit(field.output_type, schema)


def build_output_schema(
    cls: Type,
    conversions: Mapping[Type, Type] = None,
    *,
    ref_factory: Callable[[Type], str] = None,
    schema: Schema = None,
) -> JSONSchema:
    builder = OutputSchemaBuilder(conversions or {}, ref_factory)
    return builder.visit(cls, schema or Schema())
