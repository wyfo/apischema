from enum import Enum
from functools import wraps
from inspect import signature
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Pattern,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.conversions import Conversion, serializer
from apischema.types import NoneType, Number, Undefined
from apischema.validation.errors import ValidationError


class JsonType(str, Enum):
    NULL = "null"
    BOOLEAN = "boolean"
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    ARRAY = "array"
    OBJECT = "object"

    @staticmethod
    def from_type(cls: Type) -> "JsonType":
        return TYPE_TO_JSON_TYPE[cls]


class JsonTypes(Dict[type, JsonType]):
    def __missing__(self, key):
        raise TypeError(f"Invalid JSON type {key}")


TYPE_TO_JSON_TYPE = JsonTypes(
    {
        NoneType: JsonType.NULL,
        bool: JsonType.BOOLEAN,
        str: JsonType.STRING,
        int: JsonType.INTEGER,
        float: JsonType.NUMBER,
        list: JsonType.ARRAY,
        dict: JsonType.OBJECT,
    }
)


def bad_type(data: Any, *expected: type) -> ValidationError:
    msgs = [
        f"expected type {JsonType.from_type(tp)},"
        f" found {JsonType.from_type(data.__class__)}"
        for tp in expected
    ]
    return ValidationError(msgs)


class JsonSchema(Dict[str, Any]):
    pass


serializer(Conversion(dict, source=JsonSchema))


Func = TypeVar("Func", bound=Callable)


def json_schema_kwargs(func: Func) -> Func:
    @wraps(func)
    def wrapper(**kwargs):
        type_ = kwargs.get("type")
        if isinstance(type_, Sequence):
            if JsonType.INTEGER in type_ and JsonType.NUMBER in type_:
                kwargs["type"] = [t for t in type_ if t != JsonType.INTEGER]
        return JsonSchema(
            (k, v)
            for k, v in kwargs.items()
            if k not in _json_schema_params or v != _json_schema_params[k].default
        )

    _json_schema_params = signature(func).parameters
    return cast(Func, wrapper)


@json_schema_kwargs
def json_schema(
    *,
    additionalProperties: Union[bool, JsonSchema] = JsonSchema(),
    allOf: Sequence[JsonSchema] = [],
    anyOf: Sequence[JsonSchema] = [],
    const: Any = Undefined,
    default: Any = Undefined,
    dependentRequired: Mapping[str, Collection[str]] = {},
    deprecated: bool = False,
    description: str = None,
    enum: Sequence[Any] = [],
    exclusiveMaximum: Number = None,
    exclusiveMinimum: Number = None,
    examples: Sequence[Any] = None,
    format: str = None,
    items: Union[bool, JsonSchema] = JsonSchema(),
    maximum: Number = None,
    minimum: Number = None,
    maxItems: int = None,
    minItems: int = None,
    maxLength: int = None,
    minLength: int = None,
    maxProperties: int = None,
    minProperties: int = None,
    multipleOf: Number = None,
    oneOf: Sequence[JsonSchema] = [],
    pattern: Pattern = None,
    patternProperties: Mapping[Pattern, JsonSchema] = {},
    prefixItems: Sequence[JsonSchema] = [],
    properties: Mapping[str, JsonSchema] = {},
    readOnly: bool = False,
    required: Sequence[str] = [],
    title: str = None,
    type: Union[JsonType, Sequence[JsonType]] = None,
    uniqueItems: bool = False,
    unevaluatedProperties: Union[bool, JsonSchema] = JsonSchema(),
    writeOnly: bool = False,
) -> JsonSchema:
    ...
