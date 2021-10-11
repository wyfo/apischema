from dataclasses import dataclass, field
from typing import Any, Callable, get_origin

import docstring_parser

from apischema import schema, serialized, settings
from apischema.json_schema import serialization_schema
from apischema.schemas import Schema
from apischema.type_names import get_type_name


@dataclass
class Foo:
    """Foo class

    :var bar: bar attribute"""

    bar: str = field(metadata=schema(max_len=10))

    @serialized
    @property
    def baz(self) -> int:
        """baz method"""
        ...


def type_base_schema(tp: Any) -> Schema | None:
    if not hasattr(tp, "__doc__"):
        return None
    return schema(
        title=get_type_name(tp).json_schema,
        description=docstring_parser.parse(tp.__doc__).short_description,
    )


def field_base_schema(tp: Any, name: str, alias: str) -> Schema | None:
    title = alias.replace("_", " ").capitalize()
    tp = get_origin(tp) or tp  # tp can be generic
    for meta in docstring_parser.parse(tp.__doc__).meta:
        if meta.args == ["var", name]:
            return schema(title=title, description=meta.description)
    return schema(title=title)


def method_base_schema(tp: Any, method: Callable, alias: str) -> Schema | None:
    return schema(
        title=alias.replace("_", " ").capitalize(),
        description=docstring_parser.parse(method.__doc__).short_description,
    )


settings.base_schema.type = type_base_schema
settings.base_schema.field = field_base_schema
settings.base_schema.method = method_base_schema

assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "additionalProperties": False,
    "title": "Foo",
    "description": "Foo class",
    "properties": {
        "bar": {
            "description": "bar attribute",
            "title": "Bar",
            "type": "string",
            "maxLength": 10,
        },
        "baz": {"description": "baz method", "title": "Baz", "type": "integer"},
    },
    "required": ["bar", "baz"],
    "type": "object",
}
