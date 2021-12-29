from dataclasses import dataclass, field

import pytest

from apischema import deserialize, settings


@dataclass
class Foo:
    no_default: int
    default: str = ""
    default_factory: list = field(default_factory=list)


@pytest.mark.parametrize("override", [True, False])
def test_override_dataclass_constructors(monkeypatch, override):
    monkeypatch.setattr(
        settings.deserialization, "override_dataclass_constructors", override
    )
    assert deserialize(Foo, {"no_default": 0}) == Foo(0, "", [])
