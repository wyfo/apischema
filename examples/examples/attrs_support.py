from functools import lru_cache
from typing import Optional

import attr

from apischema import deserialize, serialize, settings
from apischema.conversions.conversions import Conversions
from apischema.objects import ObjectField, object_conversion
from apischema.objects.conversions import DeserializationSerialization


@lru_cache()  # Use cache because it will be called often
def attrs_conversion(cls: type) -> DeserializationSerialization:
    fields = [
        ObjectField(a.name, a.type, a.default == attr.NOTHING, default=a.default)
        for a in getattr(cls, "__attrs_attrs__")
    ]
    return object_conversion(cls, fields)


prev_deserialization = settings.deserialization()
prev_serialization = settings.serialization()


@settings.deserialization
def deserialization(cls: type) -> Optional[Conversions]:
    result = prev_deserialization(cls)
    if result is not None:
        return result
    elif hasattr(cls, "__attrs_attrs__"):
        return attrs_conversion(cls).deserialization
    else:
        return None


@settings.serialization
def serialization(cls: type) -> Optional[Conversions]:
    result = prev_serialization(cls)
    if result is not None:
        return result
    elif hasattr(cls, "__attrs_attrs__"):
        return attrs_conversion(cls).serialization
    else:
        return None


@attr.s
class Foo:
    bar: int = attr.ib()


assert deserialize(Foo, {"bar": 0}) == Foo(0)
assert serialize(Foo(0)) == {"bar": 0}
