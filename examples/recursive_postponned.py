from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apischema import deserialize


@dataclass
class Node:
    value: int
    child: Optional[Node] = None


assert deserialize(Node, {"value": 0, "child": {"value": 1}}) == Node(0, Node(1))
