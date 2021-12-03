from typing import Any, Generic, TypeVar, Union
from pytest import mark

from apischema import deserializer, serializer
from apischema.json_schema import deserialization_schema, serialization_schema

T = TypeVar("T")


@deserializer
class Wrapper(Generic[T]):
    def __init__(self, value: T):
        self.value = value


@serializer
def wrapper_value(wrapper: Wrapper[T]) -> T:
    return wrapper.value


@mark.parametrize("schema_factory", [deserialization_schema, serialization_schema])  # type: ignore
@mark.parametrize("wrapper_type", [Wrapper, Wrapper[Any]])
def test_json_schema_union_any(schema_factory, wrapper_type):
    assert schema_factory(Union[int, wrapper_type], with_schema=False) == {}
