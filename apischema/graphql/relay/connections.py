from dataclasses import dataclass
from typing import Generic, Optional, Sequence, TypeVar

Cursor_ = TypeVar("Cursor_")
Node_ = TypeVar("Node_")


@dataclass
class Edge(Generic[Node_, Cursor_]):
    node: Node_
    cursor: Cursor_


@dataclass
class PageInfo(Generic[Cursor_]):
    has_previous_page: bool = False
    has_next_page: bool = False
    start_cursor: Optional[Cursor_] = None
    end_cursor: Optional[Cursor_] = None

    @staticmethod
    def from_edges(
        edges: Sequence[Optional[Edge[Node_, Cursor_]]],
        has_previous_page: bool = False,
        has_next_page: bool = False,
    ) -> "PageInfo":
        start_cursor, end_cursor = None, None
        if edges is not None:
            if edges[0] is not None:
                start_cursor = edges[0].cursor
            if edges[-1] is not None:
                end_cursor = edges[-1].cursor
        return PageInfo(has_previous_page, has_next_page, start_cursor, end_cursor)


Edge_ = TypeVar("Edge_", bound=Edge)


@dataclass
class Connection(Generic[Node_, Cursor_, Edge_]):
    edges: Optional[Sequence[Optional[Edge_]]]
    page_info: PageInfo[Cursor_]
