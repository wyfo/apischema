from typing import Any, Mapping, Optional, Type, TypeVar

import pydantic
from pydantic import BaseModel
from pytest import raises

from apischema import (
    ValidationError,
    deserialize,
    deserializer,
    schema,
    serialize,
    serializer,
    settings,
)
from apischema.json_schema import deserialization_schema
from apischema.json_schema.schema import Schema
from apischema.validation.errors import LocalizedError

Model = TypeVar("Model", bound=pydantic.BaseModel)


# Use __init_subclass__ to add a deserializer to each BaseModel derived class
# This could be replaced by overriding `settings.deserialization`
# (it would not force to assign __init_subclass__ before subclassing
# but it would add a little overhead and more code)
def __init_subclass__(cls: Type[Model]):
    def deserialize_pydantic(data: Mapping[str, Any]) -> Model:
        try:
            return cls(**data)
        except pydantic.ValidationError as error:
            new_error = ValidationError.deserialize(
                [LocalizedError(err["loc"], [err["msg"]]) for err in error.errors()]
            )
            assert new_error is not None
            raise new_error

    deserializer(deserialize_pydantic, ret=cls)


# This line must be executed before any BaseModel subclassing
BaseModel.__init_subclass__ = classmethod(__init_subclass__)  # type: ignore


@serializer
def serialize_pydantic(obj: pydantic.BaseModel) -> Mapping[str, Any]:
    # There is actually no mean to retrieve `serialize` parameters,
    # so exclude unset is set to True as it's the default apischema setting
    return obj.dict(exclude_unset=True)


prev_default_schema = settings.default_schema()


@settings.default_schema
def default_schema(cls: Any) -> Optional[Schema]:
    result = prev_default_schema(cls)
    if result:
        return result
    else:
        try:
            # issubclass can fail (e.g. with NewType)
            if not issubclass(cls, pydantic.BaseModel):
                return None
        except TypeError:
            return None
        return schema(extra=cls.schema(), extra_only=True)


class Foo(pydantic.BaseModel):
    bar: int


assert deserialize(Foo, {"bar": 0}) == Foo(bar=0)
assert serialize(Foo(bar=0)) == {"bar": 0}
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "title": "Foo",
    "type": "object",
    "properties": {"bar": {"title": "Bar", "type": "integer"}},
    "required": ["bar"],
}
with raises(ValidationError) as err:
    deserialize(Foo, {"bar": "not an int"})
assert serialize(err.value) == [
    # pydantic error message
    {"loc": ["bar"], "err": ["value is not a valid integer"]}
]
