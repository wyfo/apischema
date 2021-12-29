from dataclasses import dataclass

import pytest

from apischema import deserialize, settings


@dataclass
class Foo:
    bar: int


@pytest.mark.parametrize("override", [True, False])
def test_override_dataclass_constructors(monkeypatch, override):
    monkeypatch.setattr(
        settings.deserialization, "override_dataclass_constructors", override
    )
    assert deserialize(Foo, {"bar": 0}) == Foo(0)
