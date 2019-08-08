from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from typing import (Any, Dict, Iterable, Mapping, Optional, Sequence, Set,
                    Type, Union, get_type_hints)

from src.data import to_data
from src.errors import UNION_PATH
from src.field import NoDefault, field, get_aliased, get_default, has_default
from src.model import Model, get_model
from src.spec import Spec, get_spec
from src.types import Primitive, type_name
from src.utils import camelize
from src.visitor import Path, Visitor

# TODO: handle default
# TODO fix broken specs
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


class SchemaBuilder(Visitor[Schema, Optional[Spec]]):
    def __init__(self, camel_case=True, spec_key="spec"):
        super().__init__()
        self.schemas: Set[str] = set()
        self.camel_case = camel_case
        self.spec_key = spec_key

    def with_class_context(self, cls: Type, ctx: Optional[Spec],
                           path: Path) -> Optional[Spec]:
        return merge_specs(get_spec(cls), ctx)

    def any(self, spec: Optional[Spec], path: Path) -> Schema:
        return Schema(**asdict(spec or Spec()))

    def model(self, cls: Type[Model], spec: Optional[Spec],
              path: Path) -> Schema:
        return self.visit(get_model(cls), spec, path)

    def optional(self, value: Type, spec: Optional[Spec],
                 path: Path) -> Schema:
        tmp = self.visit(value, spec, path)
        tmp.nullable = True
        return tmp

    def union(self, alternatives: Iterable[Type],
              spec: Optional[Spec], path: Path) -> Schema:
        return Schema(any_of=[
            self.visit(cls, spec,
                       (*path, UNION_PATH.format(index=i, cls=type_name(cls))))
            for i, cls in enumerate(alternatives)])

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 spec: Optional[Spec], path: Path) -> Schema:
        return Schema(type="array",
                      items=self.visit(value_type, None, (*path, "items")),
                      **opt_dict(spec))

    def mapping(self, key_type: Type, value_type: Type,
                spec: Optional[Spec], path: Path) -> Schema:
        return Schema(type="object",
                      additional_properties=self.visit(value_type, None,
                                                       (*path, "properties")),
                      **opt_dict(spec))

    def primitive(self, cls: Primitive, spec: Optional[Spec],
                  path: Path) -> Schema:
        return Schema(type=PRIMITIVE_TYPES_MAP[cls],
                      **opt_dict(spec))

    def dataclass(self, cls: Type, spec: Optional[Spec], path: Path) -> Schema:
        assert is_dataclass(cls)
        if cls.__name__ in self.schemas:
            return ref(cls.__name__)
        self.schemas.add(cls.__name__)
        type_hints = get_type_hints(cls)
        properties = {}
        # noinspection PyDataclass
        for field in fields(cls):  # noqa F402
            alias = camelize(get_aliased(field), self.camel_case)
            schema = self.visit(type_hints[field.name],
                                getattr(field, self.spec_key, None),
                                (*path, alias))
            try:
                schema.default = to_data(type_hints[field.name],
                                         get_default(field))
            except NoDefault:
                pass
            properties[alias] = schema
        # noinspection PyDataclass,PyShadowingNames
        return Schema(type="object",
                      required=[camelize(get_aliased(field), self.camel_case)
                                for field in fields(cls)
                                if not has_default(field)],
                      properties=properties,
                      **opt_dict(spec))

    def enum(self, cls: Type[Enum], spec: Optional[Spec],
             path: Path) -> Schema:
        return self.literal([elt.value for elt in cls], spec, path)

    def literal(self, values: Sequence[Any], spec: Optional[Spec],
                path: Path) -> Schema:
        types = set(map(type, values))
        type_ = None
        one_of = None
        if len(types) > 1:
            one_of = [Schema(type=t.__name__) for t in types]
        else:
            type_ = next(iter(types)).__name__
        return Schema(type=type_, enum=values, one_of=one_of)


def build_schema(cls: Type, camel_case=True, spec_key="spec") -> Schema:
    return SchemaBuilder(camel_case, spec_key).visit(cls, None, ())
