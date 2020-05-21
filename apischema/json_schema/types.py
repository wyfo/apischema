from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Pattern, Sequence, Type, Union

from apischema.alias import alias
from apischema.fields import with_fields_set
from apischema.types import NoneType, Number
from apischema.utils import NO_DEFAULT, to_camel_case


class JSONType(Enum):
    NULL = "null"
    BOOLEAN = "boolean"
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    ARRAY = "array"
    OBJECT = "object"

    @staticmethod
    def from_type(cls: Type) -> "JSONType":
        return {
            NoneType: JSONType.NULL,
            bool: JSONType.BOOLEAN,
            str: JSONType.STRING,
            int: JSONType.INTEGER,
            float: JSONType.NUMBER,
            list: JSONType.ARRAY,
            dict: JSONType.OBJECT,
        }[cls]


@alias(to_camel_case)
@with_fields_set
@dataclass
class JSONSchema:
    additional_properties: Optional[Union[bool, "JSONSchema"]] = None
    all_of: Optional[Sequence["JSONSchema"]] = None
    any_of: Optional[Sequence["JSONSchema"]] = None
    const: Any = NO_DEFAULT
    default: Any = NO_DEFAULT
    description: Optional[str] = None
    enum: Optional[Sequence[Any]] = None
    exclusive_maximum: Optional[Number] = None
    exclusive_minimum: Optional[Number] = None
    examples: Optional[Sequence[Any]] = None
    format: Optional[str] = None
    items: Optional[Union["JSONSchema", Sequence["JSONSchema"]]] = None
    maximum: Optional[Number] = None
    minimum: Optional[Number] = None
    max_items: Optional[int] = None
    min_items: Optional[int] = None
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    max_properties: Optional[int] = None
    min_properties: Optional[int] = None
    multiple_of: Optional[Number] = None
    one_of: Optional[Sequence["JSONSchema"]] = None
    pattern: Optional[Union[str, Pattern]] = None
    pattern_properties: Optional[Mapping[Union[str, Pattern], "JSONSchema"]] = None
    properties: Optional[Mapping[str, "JSONSchema"]] = None
    read_only: Optional[bool] = None
    ref: Optional[str] = field(default=None, metadata=alias("$ref"))
    required: Optional[Sequence[str]] = None
    title: Optional[str] = None
    type: Optional[Union[JSONType, Sequence[JSONType]]] = None
    unique_items: Optional[bool] = None
    write_only: Optional[bool] = None
