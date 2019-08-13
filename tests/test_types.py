from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional

from apischema.types import is_resolved, resolve_types


@dataclass
class Dataclass:
    a: Optional[Dataclass]


def test_resolve_types():
    assert not is_resolved(Dataclass)
    assert fields(Dataclass)[0].type == "Optional[Dataclass]"

    resolve_types(Dataclass)
    assert is_resolved(Dataclass)
    assert fields(Dataclass)[0].type == Optional[Dataclass]
