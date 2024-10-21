from enum import Enum
from functools import wraps
from inspect import signature
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Optional,
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
        try:
            return TYPE_TO_JSON_TYPE[cls]
        except KeyError:  # pragma: no cover
            raise TypeError(f"Invalid JSON type {cls}")

    def __repr__(self):
        return f"'{self.value}'"  # pragma: no cover

    def __str__(self):
        return self.value


TYPE_TO_JSON_TYPE = {
    NoneType: JsonType.NULL,
    bool: JsonType.BOOLEAN,
    str: JsonType.STRING,
    int: JsonType.INTEGER,
    float: JsonType.NUMBER,
    list: JsonType.ARRAY,
    dict: JsonType.OBJECT,
}


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
            if k not in _json_schema_params
            or (
                v != _json_schema_params[k].default
                if _json_schema_params[k].default is not True
                else v not in (True, JsonSchema())
            )
        )

    _json_schema_params = signature(func).parameters
    return cast(Func, wrapper)


@json_schema_kwargs  # type: ignore
def json_schema(
    *,
    additionalProperties: Union[bool, JsonSchema] = True,
    allOf: Sequence[JsonSchema] = [],
    anyOf: Sequence[JsonSchema] = [],
    const: Any = Undefined,
    default: Any = Undefined,
    dependentRequired: Mapping[str, Collection[str]] = {},
    deprecated: bool = False,
    description: Optional[str] = None,
    enum: Sequence[Any] = [],
    exclusiveMaximum: Optional[Number] = None,
    exclusiveMinimum: Optional[Number] = None,
    examples: Optional[Sequence[Any]] = None,
    format: Optional[str] = None,
    items: Union[bool, JsonSchema] = True,
    maximum: Optional[Number] = None,
    minimum: Optional[Number] = None,
    maxItems: Optional[int] = None,
    minItems: Optional[int] = None,
    maxLength: Optional[int] = None,
    minLength: Optional[int] = None,
    maxProperties: Optional[int] = None,
    minProperties: Optional[int] = None,
    multipleOf: Optional[Number] = None,
    oneOf: Sequence[JsonSchema] = [],
    pattern: Optional[Pattern] = None,
    patternProperties: Mapping[Pattern, JsonSchema] = {},
    prefixItems: Sequence[JsonSchema] = [],
    properties: Mapping[str, JsonSchema] = {},
    readOnly: bool = False,
    required: Sequence[str] = [],
    title: Optional[str] = None,
    type: Optional[Union[JsonType, Sequence[JsonType]]] = None,
    uniqueItems: bool = False,
    unevaluatedProperties: Union[bool, JsonSchema] = True,
    writeOnly: bool = False,
) -> JsonSchema: ...
