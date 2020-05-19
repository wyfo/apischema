from dataclasses import dataclass
from typing import Any, Generic, TypeVar, Union

from pytest import raises
from typing_extensions import Annotated

from apischema import (Ignored, ValidationError, build_input_schema, from_data, schema,
                       to_data, with_fields_set)


class NoResult:
    pass


NO_RESULT = NoResult()

T = TypeVar("T")


@with_fields_set
@dataclass
class Error(Exception):
    code: int
    description: str
    data: Any = ...


@schema(min_properties=1, max_properties=1)
@with_fields_set
@dataclass
class Result(Generic[T]):
    result: Union[T, Annotated[NoResult, Ignored]] = NO_RESULT
    error: Union[Error, Annotated[None, Ignored]] = None

    def get(self) -> T:
        if self.error is not None:
            raise self.error
        assert not isinstance(self.result, NoResult)
        return self.result


def test_result():
    assert to_data(build_input_schema(Result[int])) == {
        "additionalProperties": False,
        "maxProperties":        1,
        "minProperties":        1,
        "properties":           {
            "result": {"type": "integer"},
            "error": {
                "additionalProperties": False,
                "properties":           {
                    "code":        {"type": "integer"},
                    "description": {"type": "string"},
                    "data":        {}
                },
                "required":             ["code", "description"],
                "type":                 "object"
            },
        },
        "type":                 "object"
    }

    data = {"result": 0}
    with raises(ValidationError):
        from_data(Result[str], data)
    result = from_data(Result[int], data)
    assert result.get() == 0
    assert to_data(result) == {"result": 0}

    error = from_data(Result, {"error": {"code": 42, "description": "..."}})
    with raises(Error) as err:
        error.get()
    assert err.value == Error(42, "...")
