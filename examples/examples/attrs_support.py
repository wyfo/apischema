from typing import Optional, Sequence

import attr

from apischema import deserialize, serialize, settings
from apischema.json_schema import deserialization_schema
from apischema.objects import ObjectField


prev_default_object_fields = settings.default_object_fields()


@settings.default_object_fields
def attrs_fields(cls: type) -> Optional[Sequence[ObjectField]]:
    if hasattr(cls, "__attrs_attrs__"):
        return [
            ObjectField(
                a.name, a.type, required=a.default == attr.NOTHING, default=a.default
            )
            for a in getattr(cls, "__attrs_attrs__")
        ]
    else:
        return prev_default_object_fields(cls)


@attr.s
class Foo:
    bar: int = attr.ib()


assert deserialize(Foo, {"bar": 0}) == Foo(0)
assert serialize(Foo(0)) == {"bar": 0}
assert deserialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"type": "integer"}},
    "required": ["bar"],
    "additionalProperties": False,
}
