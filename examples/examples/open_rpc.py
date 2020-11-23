from dataclasses import dataclass
from typing import Generic, TypeVar, Union

from pytest import raises

from apischema import (
    Undefined,
    UndefinedType,
    ValidationError,
    deserialize,
    schema,
    serialize,
)
from apischema.json_schema import deserialization_schema

T = TypeVar("T")


@dataclass
class Error(Exception, Generic[T]):
    code: int
    description: str
    data: Union[T, UndefinedType] = Undefined


@schema(min_props=1, max_props=1)
@dataclass
class Result(Generic[T]):
    result: Union[T, UndefinedType] = Undefined
    error: Union[Error, UndefinedType] = Undefined

    def get(self) -> T:
        if self.error is not Undefined:
            raise self.error
        else:
            assert self.result is not Undefined
            return self.result


assert deserialization_schema(Result[list[int]]) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "additionalProperties": False,
    "maxProperties": 1,
    "minProperties": 1,
    "properties": {
        "result": {"type": "array", "items": {"type": "integer"}},
        "error": {
            "additionalProperties": False,
            "properties": {
                "code": {"type": "integer"},
                "description": {"type": "string"},
                "data": {},
            },
            "required": ["code", "description"],
            "type": "object",
        },
    },
    "type": "object",
}

data = {"result": 0}
with raises(ValidationError):
    deserialize(Result[str], data)
result = deserialize(Result[int], data)
assert result == Result(0)
assert result.get() == 0
assert serialize(result) == {"result": 0}

error = deserialize(Result, {"error": {"code": 42, "description": "..."}})
with raises(Error) as err:
    error.get()
assert err.value == Error(42, "...")
