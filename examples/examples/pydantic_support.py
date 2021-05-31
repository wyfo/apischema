from collections.abc import Mapping
from typing import Any, Optional

import pydantic
from pytest import raises

from apischema import (
    ValidationError,
    deserialize,
    schema,
    serialize,
    serializer,
    settings,
)
from apischema.conversions import Conversion, Conversions
from apischema.json_schema import Schema, deserialization_schema
from apischema.validation.errors import LocalizedError

#################### Pydantic support code starts here

prev_deserialization = settings.deserialization.default_conversions


def default_deserialization(cls: type) -> Optional[Conversions]:
    if issubclass(cls, pydantic.BaseModel):

        def deserialize_pydantic(data):
            try:
                return cls.parse_obj(data)
            except pydantic.ValidationError as error:
                raise ValidationError.deserialize(
                    [LocalizedError(err["loc"], [err["msg"]]) for err in error.errors()]
                )

        return Conversion(
            deserialize_pydantic,
            source=cls.__annotations__.get("__root__", Mapping[str, Any]),
            target=cls,
        )
    else:
        return prev_deserialization(cls)


settings.deserialization.default_conversions = default_deserialization

prev_schema = settings.default_schema


def default_schema(tp: Any) -> Optional[Schema]:
    if isinstance(tp, type) and issubclass(tp, pydantic.BaseModel):
        return schema(extra=tp.schema(), override=True)
    else:
        return prev_schema(tp)


settings.default_schema = default_schema

# No need to use settings.serialization because serializer is inherited
@serializer
def serialize_pydantic(obj: pydantic.BaseModel) -> Any:
    # There is currently no way to retrieve `serialize` parameters inside converters,
    # so exclude_unset is set to True as it's the default apischema setting
    return getattr(obj, "__root__", obj.dict(exclude_unset=True))


#################### Pydantic support code ends here


class Foo(pydantic.BaseModel):
    bar: int


assert deserialize(Foo, {"bar": 0}) == Foo(bar=0)
assert serialize(Foo(bar=0)) == {"bar": 0}
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "title": "Foo",  # pydantic title
    "type": "object",
    "properties": {"bar": {"title": "Bar", "type": "integer"}},
    "required": ["bar"],
}
with raises(ValidationError) as err:
    deserialize(Foo, {"bar": "not an int"})
assert serialize(err.value) == [
    {"loc": ["bar"], "err": ["value is not a valid integer"]}  # pydantic error message
]
