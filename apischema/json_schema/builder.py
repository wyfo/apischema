from dataclasses import (Field, InitVar, _FIELD_INITVAR, fields,  # type: ignore
                         is_dataclass, replace)
from enum import Enum
from itertools import chain
from typing import (Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence,
                    Set, Tuple, Type, Union)

from apischema.alias import ALIAS_METADATA
from apischema.conversion import (Converter, INPUT_METADATA, InputVisitorMixin,
                                  OUTPUT_METADATA, OutputVisitorMixin)
from apischema.data import to_data
from apischema.fields import (NoDefault, fields_set, get_default, has_default,
                              init_fields,
                              mark_set_fields)
from apischema.ignore import Ignored
from apischema.json_schema.types import JSONSchema, JSONType
from apischema.properties import PROPERTIES_METADATA
from apischema.schema import Constraint, Schema
from apischema.schema.annotations import ANNOTATIONS_METADATA, get_annotations
from apischema.schema.constraints import (ArrayConstraint, CONSTRAINT_METADATA,
                                          NumberConstraint, ObjectConstraint,
                                          StringConstraint, get_constraint)
from apischema.typing import get_type_hints
from apischema.utils import NO_DEFAULT, as_dict
from apischema.visitor import Visitor

constraint_by_type = {
    int:   NumberConstraint,
    float: NumberConstraint,
    str:   StringConstraint,
}


class ReadWriteOnly(Constraint):
    pass


def check_constraint(schema: Schema, expected: Type[Constraint]):
    if schema.constraint is not None:
        if not isinstance(schema.constraint, expected):
            if not isinstance(schema.constraint, ReadWriteOnly):
                raise TypeError(f"Bad constraint: expected {expected.__name__}"
                                f" found {type(schema.constraint).__name__}")


def _remove_none(obj: Optional[Any]) -> Iterable[Tuple[str, Any]]:
    if obj is None:
        return iter(())
    return ((k, v) for k, v in as_dict(obj).items()
            if v is not None and v is not NO_DEFAULT
            and k not in ("items", "additional_properties"))


def _to_dict(schema: Schema) -> Mapping[str, Any]:
    return dict(chain(_remove_none(schema.annotations),
                      _remove_none(schema.constraint)))


def _merge_constraints(c1: Optional[Constraint],
                       c2: Optional[Constraint]) -> Optional[Constraint]:
    if c1 is None:
        return c2
    if c2 is None:
        return c1
    if isinstance(c1, ReadWriteOnly):
        return type(c2)(**{**as_dict(c1), **as_dict(c2)})
    elif Constraint != type(c1) != type(c2) != Constraint:
        raise TypeError(f"Incompatibles constraints {type(c1).__name__}"
                        f" and {type(c2).__name__}")
    return c1


def _override(schema: Schema, cls: Type) -> Schema:
    return Schema(schema.annotations or get_annotations(cls),
                  _merge_constraints(schema.constraint, get_constraint(cls)))


def _field_schema(field: Field) -> Schema:
    return Schema(field.metadata.get(ANNOTATIONS_METADATA),
                  field.metadata.get(CONSTRAINT_METADATA))


class SchemaBuilder(Visitor[Schema, JSONSchema]):
    def __init__(self, ref_factory: Optional[Callable[[Type], str]]):
        super().__init__()
        self.ref_factory = ref_factory or self._missing_ref_factory
        self.schemas: Set[Type] = set()

    @staticmethod
    def _missing_ref_factory(cls: Type) -> str:
        raise TypeError("reference factory is needed to handle"
                        " recursive types")

    def primitive(self, cls: Type, schema: Schema) -> JSONSchema:
        if cls in constraint_by_type:
            check_constraint(schema, constraint_by_type[cls])
        return JSONSchema(type=JSONType.from_type(cls), **_to_dict(schema))

    def union(self, alternatives: Sequence[Type],
              schema: Schema) -> JSONSchema:
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

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 schema: Schema) -> JSONSchema:
        check_constraint(schema, ArrayConstraint)
        if isinstance(schema.items_, Sequence):
            raise TypeError("Iterable items schema cannot be a list of schema")
        return JSONSchema(type=JSONType.ARRAY,
                          items=self.visit(value_type, schema.items_),
                          **_to_dict(schema))

    def mapping(self, cls: Type[Mapping], key_type: Type, value_type: Type,
                schema: Schema) -> JSONSchema:
        check_constraint(schema, ObjectConstraint)
        props = self.visit(value_type, schema.additional_properties)
        return JSONSchema(type=JSONType.OBJECT, additional_properties=props,
                          **_to_dict(schema))

    def typed_dict(self, cls: Type, keys: Mapping[str, Type], total: bool,
                   schema: Schema) -> JSONSchema:
        if cls in self.schemas:
            return JSONSchema(ref=self.ref_factory(cls))
        check_constraint(schema, ObjectConstraint)
        if schema.additional_properties:
            raise TypeError("additional properties are not handled"
                            " for TypedDict")
        types = get_type_hints(cls)
        sorted_keys = sorted(keys)
        return JSONSchema(type=JSONType.OBJECT,
                          properties={key: self.visit(types[key], Schema())
                                      for key in sorted_keys},
                          required=sorted_keys if total else [],
                          additional_properties=True, **_to_dict(schema))

    def tuple(self, types: Sequence[Type], schema: Schema) -> JSONSchema:
        check_constraint(schema, ArrayConstraint)
        if schema.constraint is not None:
            assert isinstance(schema.constraint, ArrayConstraint)
            if (schema.constraint.max_items is not None
                    or schema.constraint.min_items is not None):
                raise TypeError("Tuple cannot have min_items/max_items"
                                " constraint")
        if isinstance(schema.items_, Sequence):
            if len(schema.items_) != len(types):
                raise TypeError("Tuple items schema list must have the same"
                                " length than tuple")
        items = []
        for i, cls in enumerate(types):
            if isinstance(schema.items_, Sequence):
                elt_schema = schema.items_[i]
            else:
                elt_schema = schema.items_
            items.append(self.visit(cls, elt_schema))
        return JSONSchema(type=JSONType.ARRAY, items=items,
                          min_items=len(types), max_items=len(types),
                          **_to_dict(schema))

    def literal(self, values: Sequence[Any], schema: Schema) -> JSONSchema:
        if not values:
            raise TypeError("empty Literal")
        if schema.constraint is not None:
            raise TypeError("Literal cannot have constraint")
        types = sorted(set(
            JSONType.from_type(type(v.value if isinstance(v, Enum) else v))
            for v in values
        ))
        type_ = types[0] if len(types) == 1 else types
        if len(values) == 1:
            return JSONSchema(type=type_, const=values[0],  # type: ignore
                              **_to_dict(schema))
        else:
            return JSONSchema(type=type_, enum=values,  # type: ignore
                              **_to_dict(schema))

    def _dataclass_fields(self, cls: Type) -> Iterable[Field]:
        raise NotImplementedError()

    def _set_field_default(self, field: Field, schema: Schema):
        if schema.annotations is not None and schema.annotations.default is ...:
            try:
                default = to_data(get_default(field))
            except NoDefault:
                raise TypeError("Invalid ... as default without field default")
            schema.annotations = replace(schema.annotations, default=default)

    def _field_visit(self, field: Field, types: Mapping[str, Type]
                     ) -> JSONSchema:
        raise NotImplementedError()

    def dataclass(self, cls: Type, schema: Schema) -> JSONSchema:
        assert is_dataclass(cls)
        if cls in self.schemas:
            return JSONSchema(ref=self.ref_factory(cls))
        self.schemas.add(cls)
        check_constraint(schema, ObjectConstraint)
        schema_ = _override(schema, cls)
        properties = {}
        additional_field: Optional[Field] = None
        pattern_fields: List[Field] = []
        types = get_type_hints(cls)
        required: List[str] = []
        for field in self._dataclass_fields(cls):
            if PROPERTIES_METADATA in field.metadata:
                if field.metadata[PROPERTIES_METADATA] is None:
                    if additional_field is not None:
                        raise TypeError("Multiple properties without pattern")
                    additional_field = field
                else:
                    pattern_fields.append(field)
                continue
            alias = field.metadata.get(ALIAS_METADATA, field.name)
            properties[alias] = self._field_visit(field, types)
            if not has_default(field):
                required.append(alias)
        pattern_properties: Dict[str, Any] = {
            field.metadata[PROPERTIES_METADATA].pattern: self._field_visit(field, types)
            for field in pattern_fields
        }
        additional_properties: Optional[Union[bool, "JSONSchema"]] = False
        if additional_field:
            additional_properties = self._field_visit(additional_field, types)
        others: Dict[str, Any] = {}
        if required:
            others["required"] = required
        if pattern_properties:
            others["pattern_properties"] = pattern_properties
        return JSONSchema(type=JSONType.OBJECT,  # type: ignore
                          properties=properties,
                          additional_properties=additional_properties,
                          **others, **_to_dict(schema_))

    def enum(self, cls: Type[Enum], schema: Schema) -> JSONSchema:
        if schema.constraint is not None:
            raise TypeError("enum cannot have constraint")
        if len(cls) == 0:
            raise TypeError("Empty enum")
        return self.literal(list(cls), _override(schema, cls))

    def new_type(self, cls: Type, super_type: Type, schema: Schema
                 ) -> JSONSchema:
        return self.visit(super_type, _override(schema, cls))

    def any(self, schema: Schema) -> JSONSchema:
        if schema.constraint is not None:
            raise TypeError("Any type cannot have constraint")
        return JSONSchema()

    def annotated(self, cls: Type, annotations: Sequence[Any],
                  schema: Schema) -> JSONSchema:
        schema_ = schema
        if Ignored in annotations:
            raise Ignored
        for annotation in annotations:
            if isinstance(annotation, Schema):
                schema_ = Schema(
                    schema.annotations or annotation.annotations,
                    _merge_constraints(schema.constraint,
                                       annotation.constraint)
                )
                break
        return self.visit(cls, schema_)


class InputSchemaBuilder(InputVisitorMixin[Schema, JSONSchema], SchemaBuilder):
    def __init__(self, ref_factory: Optional[Callable[[Type], str]],
                 additional_properties: bool):
        SchemaBuilder.__init__(self, ref_factory)
        self.additional_properties = additional_properties

    def _custom(self, cls: Type, custom: Dict[Type, Converter],
                schema: Schema) -> JSONSchema:
        return self.union(list(custom), _override(schema, cls))

    def _dataclass_fields(self, cls: Type) -> Iterable[Field]:
        return init_fields(cls)

    def _field_visit(self, field: Field, types: Mapping[str, Type]
                     ) -> JSONSchema:
        if INPUT_METADATA in field.metadata:
            cls, _ = field.metadata[INPUT_METADATA]
        else:
            cls = types[field.name]
        if isinstance(cls, InitVar):
            cls = cls.type  # type: ignore
        schema = _field_schema(field)
        self._set_field_default(field, schema)
        if field._field_type == _FIELD_INITVAR:  # type: ignore
            if schema.constraint is None:
                schema.constraint = ReadWriteOnly(write_only=True)
            else:
                if schema.constraint.read_only:
                    raise TypeError("InitVar cannot be read-only")
                schema.constraint = replace(schema.constraint, write_only=True)
        return self.visit(cls, schema)

    def dataclass(self, cls: Type, schema: Schema) -> JSONSchema:
        json_schema = super().dataclass(cls, schema)
        if json_schema.additional_properties is False:
            # TODO document that `dataclasses.replace` don't keep fields set
            return mark_set_fields(replace(
                json_schema, additional_properties=self.additional_properties
            ), *fields_set(json_schema), overwrite=True)
        return json_schema


def build_input_schema(cls: Type, *, ref_factory: Callable[[Type], str] = None,
                       additional_properties: bool = False,
                       schema: Schema = None) -> JSONSchema:
    builder = InputSchemaBuilder(ref_factory, additional_properties)
    return builder.visit(cls, schema or Schema())


class OutputSchemaBuilder(OutputVisitorMixin[Schema, JSONSchema],
                          SchemaBuilder):
    def __init__(self, conversions: Mapping[Type, Type],
                 ref_factory: Optional[Callable[[Type], str]]):
        SchemaBuilder.__init__(self, ref_factory)
        OutputVisitorMixin.__init__(self, conversions)

    def _custom(self, cls: Type, custom: Tuple[Type, Converter],
                schema: Schema) -> JSONSchema:
        return self.visit(custom[0], _override(schema, cls))

    def _dataclass_fields(self, cls: Type) -> Iterable[Field]:
        assert is_dataclass(cls)
        return fields(cls)

    def _field_visit(self, field: Field, types: Mapping[str, Type]
                     ) -> JSONSchema:
        if OUTPUT_METADATA in field.metadata:
            cls, _ = field.metadata[OUTPUT_METADATA]
        else:
            cls = types[field.name]
        schema = _field_schema(field)
        self._set_field_default(field, schema)
        if not field.init:
            if schema.constraint is None:
                schema.constraint = ReadWriteOnly(read_only=True)
            else:
                if schema.constraint.write_only:
                    raise TypeError("not init field cannot be write-only")
                schema.constraint = replace(schema.constraint, read_only=True)
        return self.visit(cls, schema)


def build_output_schema(cls: Type, conversions: Mapping[Type, Type] = None, *,
                        ref_factory: Callable[[Type], str] = None,
                        schema: Schema = None) -> JSONSchema:
    builder = OutputSchemaBuilder(conversions or {}, ref_factory)
    return builder.visit(cls, schema or Schema())
