from dataclasses import dataclass
from typing import Any, Generic, TypeVar, Union

from pytest import raises
from typing_extensions import Annotated

from apischema import NotNull, Skip, ValidationError, deserialize, schema, serialize
from apischema.fields import with_fields_set
from apischema.json_schema import deserialization_schema


class NoResult:
    pass


NO_RESULT = NoResult()
NO_DATA = object()

T = TypeVar("T")


@with_fields_set
@dataclass
class Error(Exception, Generic[T]):
    code: int
    description: str
    data: Any = NO_DATA


@schema(min_props=1, max_props=1)
@with_fields_set
@dataclass
class Result(Generic[T]):
    result: Union[T, Annotated[NoResult, Skip]] = NO_RESULT
    error: NotNull[Error] = None

    def get(self) -> T:
        if self.error is not None:
            raise self.error
        assert not isinstance(self.result, NoResult)
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
