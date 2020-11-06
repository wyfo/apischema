from dataclasses import field, fields, make_dataclass
from functools import lru_cache
from typing import Optional

import attr

from apischema import deserialize, serialize, settings
from apischema.conversions import Conversions, Deserialization, Serialization


@lru_cache()
def attrs_to_dataclass(cls: type) -> type:
    assert hasattr(cls, "__attrs_attrs__")
    fields_without_default = [
        (a.name, a.type) for a in cls.__attrs_attrs__ if a.default == attr.NOTHING
    ]
    fields_with_default = [
        (a.name, a.type, field(default=a.default))
        for a in cls.__attrs_attrs__
        if a.default != attr.NOTHING
    ]
    return make_dataclass(cls.__name__, fields_without_default + fields_with_default)


prev_deserialization = settings.deserialization()
prev_serialization = settings.serialization()


@settings.deserialization
def deserialization(
    cls: type, conversions: Optional[Conversions]
) -> Optional[Deserialization]:
    result = prev_deserialization(cls, conversions)
    if result is not None:
        return result
    elif hasattr(cls, "__attrs_attrs__"):
        source = attrs_to_dataclass(cls)

        def converter(source_obj):
            return cls(**{f.name: getattr(source_obj, f.name) for f in fields(source)})

        return {source: (converter, None)}
    else:
        return None


@settings.serialization
def serialization(
    cls: type, conversions: Optional[Conversions]
) -> Optional[Serialization]:
    result = prev_serialization(cls, conversions)
    if result is not None:
        return result
    elif hasattr(cls, "__attrs_attrs__"):
        target = attrs_to_dataclass(cls)

        def converter(obj):
            return target(**{a.name: getattr(obj, a.name) for a in cls.__attrs_attrs__})

        return target, (converter, None)
    else:
        return None


@attr.s
class Foo:
    bar: int = attr.ib()


assert deserialize(Foo, {"bar": 0}) == Foo(0)
assert serialize(Foo(0)) == {"bar": 0}
