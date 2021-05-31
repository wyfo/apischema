from dataclasses import dataclass, field

from apischema import alias
from apischema.objects import object_fields


@alias(lambda s: f"prefixed_{s}")
@dataclass
class Data:
    not_aliased: int = field(metadata=alias(override=False))
    not_prefixed: int = field(metadata=alias("not_overridden", override=False))
    prefixed: int
    prefixed_alias: str = field(metadata=alias("alias"))


def test_alias():
    assert {name: field.alias for name, field in object_fields(Data).items()} == {
        "not_aliased": "not_aliased",
        "not_prefixed": "not_overridden",
        "prefixed": "prefixed_prefixed",
        "prefixed_alias": "prefixed_alias",
    }
