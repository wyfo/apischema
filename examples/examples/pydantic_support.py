import inspect
from collections.abc import Mapping
from typing import Any

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
from apischema.conversions import AnyConversion, Conversion
from apischema.json_schema import deserialization_schema
from apischema.schemas import Schema

# ---------- Pydantic support code starts here ----------
prev_deserialization = settings.deserialization.default_conversion


def default_deserialization(tp: Any) -> AnyConversion | None:
    if inspect.isclass(tp) and issubclass(tp, pydantic.BaseModel):

        def deserialize_pydantic(data):
            try:
                return tp.parse_obj(data)
            except pydantic.ValidationError as error:
                raise ValidationError.from_errors(error.errors())

        return Conversion(
            deserialize_pydantic,
            source=tp.__annotations__.get("__root__", Mapping[str, Any]),
            target=tp,
        )
    else:
        return prev_deserialization(tp)


settings.deserialization.default_conversion = default_deserialization

prev_schema = settings.base_schema.type


def default_schema(tp: Any) -> Schema | None:
    if inspect.isclass(tp) and issubclass(tp, pydantic.BaseModel):
        return schema(extra=tp.schema(), override=True)
    else:
        return prev_schema(tp)


settings.base_schema.type = default_schema

# No need to use settings.serialization because serializer is inherited
@serializer
def serialize_pydantic(obj: pydantic.BaseModel) -> Any:
    # There is currently no way to retrieve `serialize` parameters inside converters,
    # so exclude_unset is set to True as it's the default apischema setting
    return getattr(obj, "__root__", obj.dict(exclude_unset=True))


# ---------- Pydantic support code ends here ----------


class Foo(pydantic.BaseModel):
    bar: int


assert deserialize(Foo, {"bar": 0}) == Foo(bar=0)
assert serialize(Foo, Foo(bar=0)) == {"bar": 0}
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "title": "Foo",  # pydantic title
    "type": "object",
    "properties": {"bar": {"title": "Bar", "type": "integer"}},
    "required": ["bar"],
}
with raises(ValidationError) as err:
    deserialize(Foo, {"bar": "not an int"})
assert err.value.errors == [
    {"loc": ["bar"], "err": "value is not a valid integer"}  # pydantic error message
]
