from collections.abc import Mapping
from typing import Any, NewType

import pydantic
from pytest import raises

from apischema import (
    ValidationError,
    deserialize,
    deserializer,
    schema,
    serialize,
    serializer,
)
from apischema.json_schema import deserialization_schema
from apischema.validation.errors import LocalizedError

#################### Pydantic support code starts here


def add_deserializer(cls: type[pydantic.BaseModel]):
    Data = NewType("Data", Mapping[str, Any])
    schema(extra=cls.schema(), override=True)(Data)

    def deserialize_pydantic(data: Mapping[str, Any]) -> pydantic.BaseModel:
        try:
            return cls(**data)
        except pydantic.ValidationError as error:
            raise ValidationError.deserialize(
                [LocalizedError(err["loc"], [err["msg"]]) for err in error.errors()]
            )

    deserializer(deserialize_pydantic, Data, cls)


for cls in pydantic.BaseModel.__subclasses__():
    add_deserializer(cls)
pydantic.BaseModel.__init_subclass__ = classmethod(add_deserializer)  # type: ignore


@serializer
def serialize_pydantic(obj: pydantic.BaseModel) -> Mapping[str, Any]:
    # There is currently no mean to retrieve `serialize` parameters,
    # so exclude unset is set to True as it's the default apischema setting
    return obj.dict(exclude_unset=True)


#################### Pydantic support code ends here


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
    {"loc": ["bar"], "err": ["value is not a valid integer"]}  # pydantic error message
]
