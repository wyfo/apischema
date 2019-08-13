from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from typing import (Any, Dict, Iterable, Mapping, Optional, Sequence, Set,
                    Type, Union)

import humps
from tmv import Primitive

from apischema.data import to_data
from apischema.field import (NoDefault, field, get_aliased, get_default,
                             has_default)
from apischema.model import Model, get_model
from apischema.spec import Spec, get_spec
# TODO: handle default
# TODO fix broken specs
from apischema.types import is_resolved, resolve_types
from apischema.visitor import Aliaser, Visitor, camel_case_aliaser

Number = Union[int, float]


@dataclass
class Schema:
    type: Optional[str] = None
    title: Optional[str] = None
    example: Optional[Any] = None
    pattern: Optional[str] = None
    required: Optional[Sequence[str]] = None
    enum: Optional[Sequence[Any]] = None
    min: Optional[Number] = field("minimum", default=None)
    max: Optional[Number] = field("maximum", default=None)
    exc_min: Optional[Number] = field("exclusive_minimum", default=None)
    exc_max: Optional[Number] = field("exclusive_maximum", default=None)
    multiple_of: Optional[Number] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_items: Optional[int] = None
    max_items: Optional[int] = None
    unique_items: Optional[bool] = None
    min_properties: Optional[int] = None
    max_properties: Optional[int] = None
    description: Optional[str] = None
    items: Optional[Schema] = None
    properties: Optional[Mapping[str, Schema]] = None
    additional_properties: Optional[Union[bool, Schema]] = None
    default: Optional[Any] = None
    all_of: Optional[Sequence[Schema]] = None
    one_of: Optional[Sequence[Schema]] = None
    any_of: Optional[Sequence[Schema]] = None
    not_: Optional[Schema] = field("not", default=None)
    format: Optional[str] = None
    read_only: Optional[bool] = None
    write_only: Optional[bool] = None
    nullable: Optional[bool] = None
    ref: Optional[str] = field("$ref", default=None)


def merge_specs(base: Optional[Spec], override: Optional[Spec]
                ) -> Optional[Spec]:
    res: Dict[str, Any] = {}
    spec_cls = Spec
    if base is not None:
        res.update(asdict(base))
        spec_cls = type(base)
    if override is not None:
        res.update(asdict(override))
        if spec_cls is Spec:
            spec_cls = type(override)
        elif type(override) is not Spec and type(override) is not spec_cls:
            raise ValueError(f"Incompatible Spec types: "
                             f"{type(base).__name__} and "
                             f"{type(override).__name__}")
    return spec_cls(**res) if res else None


def opt_dict(spec: Optional[Spec]) -> Dict[str, Any]:
    return asdict(spec) if spec is not None else {}


PRIMITIVE_TYPES_MAP = {int:   "integer",
                       float: "number",
                       str:   "string",
                       bool:  "boolean"}


def ref(name: str) -> Schema:
    return Schema(ref=f"#/components/schemas/{name}")


# noinspection PyAbstractClass
class SchemaBuilder(Visitor[Schema, Optional[Spec]]):
    def __init__(self, spec_key="spec",
                 aliaser: Optional[Aliaser] = humps.camelize):
        super().__init__(aliaser)
        self.schemas: Set[str] = set()
        self.spec_key = spec_key

    def primitive(self, cls: Primitive, spec: Optional[Spec]) -> Schema:
        return Schema(type=PRIMITIVE_TYPES_MAP[cls],
                      **opt_dict(spec))

    def optional(self, value: Type, spec: Optional[Spec]) -> Schema:
        tmp = self.visit(value, spec)
        tmp.nullable = True
        return tmp

    def union(self, alternatives: Iterable[Type],
              spec: Optional[Spec]) -> Schema:
        return Schema(any_of=[self.visit(cls, spec) for cls in alternatives])

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 spec: Optional[Spec]) -> Schema:
        return Schema(type="array",
                      items=self.visit(value_type, None),
                      **opt_dict(spec))

    def mapping(self, key_type: Type, value_type: Type,
                spec: Optional[Spec]) -> Schema:
        return Schema(type="object",
                      additional_properties=self.visit(value_type, None),
                      **opt_dict(spec))

    def literal(self, values: Sequence[Any], spec: Optional[Spec]) -> Schema:
        types = set(map(type, values))
        type_ = None
        one_of = None
        if len(types) > 1:
            one_of = [Schema(type=t.__name__) for t in types]
        else:
            type_ = next(iter(types)).__name__
        return Schema(type=type_, enum=values, one_of=one_of)

    def custom(self, cls: Type[Model], spec: Optional[Spec]) -> Schema:
        spec = merge_specs(get_spec(cls), spec)
        return self.visit(get_model(cls), spec)

    def dataclass(self, cls: Type, spec: Optional[Spec]) -> Schema:
        assert is_dataclass(cls)
        if cls.__name__ in self.schemas:
            return ref(cls.__name__)
        self.schemas.add(cls.__name__)
        if not is_resolved(cls):
            resolve_types(cls)
        properties = {}
        # noinspection PyDataclass
        for field in fields(cls):  # noqa F402
            alias = self.aliaser(get_aliased(field))
            schema = self.visit(field.type,
                                getattr(field, self.spec_key, None))
            try:
                schema.default = to_data(field.type, get_default(field))
            except NoDefault:
                pass
            properties[alias] = schema
        # noinspection PyDataclass,PyShadowingNames
        return Schema(type="object",
                      required=[self.aliaser(get_aliased(field))
                                for field in fields(cls)
                                if not has_default(field)],
                      properties=properties,
                      **opt_dict(spec))

    def enum(self, cls: Type[Enum], spec: Optional[Spec]) -> Schema:
        return self.literal([elt.value for elt in cls], spec)


def build_schema(cls: Type, camel_case=True) -> Schema:
    aliaser = camel_case_aliaser(camel_case)
    return SchemaBuilder(aliaser=aliaser).visit(cls, None)
