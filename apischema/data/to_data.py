from dataclasses import Field, fields
from enum import Enum
from typing import (Any, Dict, Iterable, Mapping, Sequence, Tuple,
                    Type,
                    TypeVar)

from apischema.alias import ALIAS_METADATA
from apischema.conversion import (Converter, OUTPUT_METADATA,
                                  OutputVisitorMixin)
from apischema.data.common_errors import bad_literal, wrong_type
from apischema.fields import FIELDS_SET_ATTR
from apischema.properties import PROPERTIES_METADATA
from apischema.types import UNTYPED_COLLECTIONS
from apischema.typing import get_type_hints
from apischema.visitor import Visitor

UNTYPED_COLLECTIONS_IDS = set(map(id, UNTYPED_COLLECTIONS))


def check_type(obj: Any, expected: Type):
    if not isinstance(obj, expected):
        raise ValueError(wrong_type(type(obj), expected))


def check_mapping(mapping: Mapping):
    if not all(isinstance(k, str) for k in mapping):
        raise ValueError("mapping keys must be strings")
    return mapping


class ToData(OutputVisitorMixin[Any, Any], Visitor[Any, Any]):
    def __init__(self, conversions: Mapping[Type, Type], exclude_unset: bool):
        Visitor.__init__(self)
        OutputVisitorMixin.__init__(self, conversions)
        self.exclude_unset = exclude_unset

    def primitive(self, cls: Type, obj):
        check_type(obj, cls)
        return obj

    def union(self, alternatives: Sequence[Type], obj):
        for cls in alternatives:
            try:
                return self.visit(cls, obj)
            except:  # noqa
                pass
        raise ValueError(f"No union alternatives {list(alternatives)}"
                         f" matches '{type(obj)}'")

    def iterable(self, cls: Type[Iterable], value_type: Type, obj):
        check_type(obj, Iterable)
        return [self.visit(value_type, elt) for elt in obj]

    def mapping(self, cls: Type[Mapping], key_type: Type,
                value_type: Type, obj):
        check_type(obj, Mapping)
        return check_mapping({
            self.visit(key_type, key): self.visit(value_type, value)
            for key, value in obj.items()
        })

    def typed_dict(self, cls: Type, keys: Mapping[str, Type],
                   total: bool, obj):
        check_type(obj, Mapping)
        if total and any(key not in obj for key in keys):
            raise ValueError(f"Typed '{cls}' is not total: {obj}")
        return {
            key: self.visit(keys[key], value) if key in keys else value
            for key, value in obj.items()
        }

    def tuple(self, types: Sequence[Type], obj):
        check_type(obj, tuple)
        if len(obj) != len(types):
            raise ValueError(f"Expected tuple length '{len(types)}',"
                             f" got '{len(obj)}'")
        return [self.visit(cls, elt) for cls, elt in zip(types, obj)]

    def literal(self, values: Sequence[Any], obj):
        if obj not in values:
            raise ValueError(bad_literal(obj, values))
        return obj

    def _custom(self, cls: Type, custom: Tuple[Type, Converter], obj):
        conv_type, converter = custom
        return self.visit(conv_type, converter(obj))

    def dataclass(self, cls: Type, obj):
        res: Dict[str, Any] = {}
        fields_: Iterable[Field] = fields(obj)
        if self.exclude_unset and hasattr(obj, FIELDS_SET_ATTR):
            fields_ = (f for f in fields_
                       if f.name in getattr(obj, FIELDS_SET_ATTR))
        types = get_type_hints(cls)
        for field in fields_:
            if OUTPUT_METADATA in field.metadata:
                ret, converter = field.metadata[OUTPUT_METADATA]
                value = self.visit(ret, converter(getattr(obj, field.name)))
            else:
                value = self.visit(types[field.name], getattr(obj, field.name))
            if PROPERTIES_METADATA in field.metadata:
                res.update(value)
            else:
                alias = field.metadata.get(ALIAS_METADATA, field.name)
                res[alias] = value
        return res

    def enum(self, cls: Type[Enum], obj):
        check_type(obj, cls)
        return obj.value

    def any(self, obj):
        if isinstance(obj, Mapping):
            return check_mapping({
                self.visit(type(k), k): self.visit(type(v), v)
                for k, v in obj.items()
            })
        if isinstance(obj, str):
            return self.visit(type(obj), obj)
        if isinstance(obj, Iterable):
            return [self.visit(type(v), v) for v in obj]
        return self.visit(type(obj), obj)

    def visit(self, cls: Type, obj):
        # Use `id` to avoid useless costly generic types hashing
        if id(cls) in UNTYPED_COLLECTIONS_IDS:
            return self.visit(UNTYPED_COLLECTIONS[cls], obj)  # type: ignore
        return super().visit(cls, obj)


T = TypeVar("T")


def to_data(obj: T, cls: Type[T] = None,
            conversions: Mapping[Type, Type] = None,
            *, exclude_unset: bool = True) -> Any:
    if cls is None:
        cls = type(obj)
    if conversions is None:
        conversions = {}
    return ToData(conversions, exclude_unset).visit(cls, obj)
