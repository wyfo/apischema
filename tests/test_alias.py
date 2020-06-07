from dataclasses import dataclass, field, fields

from apischema import alias, settings
from apischema.json_schema import deserialization_schema
from apischema.metadata.keys import ALIAS_METADATA


@alias(lambda s: f"prefixed_{s}")
@dataclass
class Class:
    not_aliased: int = field(metadata=alias(override=False))
    not_prefixed: int = field(metadata=alias("not_overridden", override=False))
    prefixed: int
    prefixed_alias: str = field(metadata=alias("alias"))


def test_alias():
    assert {f.name: f.metadata.get(ALIAS_METADATA) for f in fields(Class)} == {
        "not_aliased": None,
        "not_prefixed": "not_overridden",
        "prefixed": "prefixed_prefixed",
        "prefixed_alias": "prefixed_alias",
    }


@dataclass
class CamelCase:
    snake_case: int


def test_global_aliaser():
    settings.aliaser(camel_case=True)
    assert deserialization_schema(CamelCase)["properties"] == {
        "snakeCase": {"type": "integer"}
    }
    settings.aliaser(camel_case=False)
    # dataclasses cache is reset
    assert deserialization_schema(CamelCase)["properties"] == {
        "snake_case": {"type": "integer"}
    }
