from dataclasses import MISSING, field, make_dataclass
from functools import lru_cache
from typing import Optional

import attr

from apischema import deserialize, serialize, settings
from apischema.conversions import dataclass_model
from apischema.conversions.conversions import Conversion, Conversions


def attrs_to_dataclass(cls: type) -> type:
    fields = [
        (
            a.name,
            a.type,
            field(default=a.default) if a.default != attr.NOTHING else MISSING,
        )
        for a in getattr(cls, "__attrs_attrs__")
    ]
    return make_dataclass(cls.__name__, fields)


@lru_cache()  # Use cache because it will be called often
def attrs_dataclass_model(cls: type) -> tuple[Conversion, Conversion]:
    return dataclass_model(cls, attrs_to_dataclass(cls))


prev_deserialization = settings.deserialization()
prev_serialization = settings.serialization()


@settings.deserialization
def deserialization(cls: type) -> Optional[Conversions]:
    result = prev_deserialization(cls)
    if result is not None:
        return result
    elif hasattr(cls, "__attrs_attrs__"):
        deserialization_conversion, _ = attrs_dataclass_model(cls)
        return deserialization_conversion
    else:
        return None


@settings.serialization
def serialization(cls: type) -> Optional[Conversions]:
    result = prev_serialization(cls)
    if result is not None:
        return result
    elif hasattr(cls, "__attrs_attrs__"):
        _, serialization_conversion = attrs_dataclass_model(cls)
        return serialization_conversion
    else:
        return None


@attr.s
class Foo:
    bar: int = attr.ib()


assert deserialize(Foo, {"bar": 0}) == Foo(0)
assert serialize(Foo(0)) == {"bar": 0}
