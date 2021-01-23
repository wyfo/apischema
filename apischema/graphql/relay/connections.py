from typing import Generic, Optional, Sequence, TypeVar

from dataclasses import dataclass, field

from apischema.graphql import resolver
from apischema.metadata import skip

Cursor_ = TypeVar("Cursor_")


@dataclass
class PageInfo(Generic[Cursor_]):
    has_previous_page: bool
    has_next_page: bool
    start_cursor: Optional[Cursor_]
    end_cursor: Optional[Cursor_]


Node_ = TypeVar("Node_")


@dataclass
class Edge(Generic[Node_, Cursor_]):
    node: Node_
    cursor: Cursor_


Edge_ = TypeVar("Edge_", bound=Edge)


@dataclass
class Connection(Generic[Node_, Cursor_, Edge_]):
    edges: Optional[Sequence[Optional[Edge_]]]
    has_previous_page: bool = field(default=False, metadata=skip)
    has_next_page: bool = field(default=False, metadata=skip)
    start_cursor: Optional[Cursor_] = field(default=None, metadata=skip)
    end_cursor: Optional[Cursor_] = field(default=None, metadata=skip)

    def page_info(self) -> PageInfo[Cursor_]:
        start_cursor, end_cursor = None, None
        if self.edges is not None:
            if self.edges[0] is not None:
                start_cursor = self.edges[0].cursor
            if self.edges[-1] is not None:
                end_cursor = self.edges[-1].cursor
        if self.start_cursor is not None:
            start_cursor = self.start_cursor
        if self.end_cursor is not None:
            end_cursor = self.end_cursor
        return PageInfo(
            has_previous_page=self.has_previous_page,
            has_next_page=self.has_next_page,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )


resolver(Connection.page_info)
