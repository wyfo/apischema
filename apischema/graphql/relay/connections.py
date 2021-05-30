from dataclasses import dataclass
from typing import Generic, Optional, Sequence, Type, TypeVar

from apischema.type_names import get_type_name, type_name
from apischema.types import NoneType
from apischema.typing import generic_mro, get_args, get_origin
from apischema.utils import get_args2, is_union_of, wrap_generic_init_subclass

Cursor_ = TypeVar("Cursor_")
Node_ = TypeVar("Node_")


def get_node_name(tp):
    if is_union_of(tp, NoneType) and len(get_args2(tp)):
        tp = next(arg for arg in get_args2(tp) if arg is not NoneType)
    ref = get_type_name(tp).graphql
    if ref is None:
        raise TypeError(
            f"Node {tp} must have a ref registered to be used with connection"
        )
    return ref


def edge_name(tp: Type["Edge"], *args) -> str:
    for base in generic_mro(tp[tuple(args)] if args else tp):  # type: ignore
        if get_origin(base) == Edge:
            return f"{get_node_name(get_args(base)[0])}Edge"
    raise NotImplementedError


@type_name(graphql=edge_name)
@dataclass
class Edge(Generic[Node_, Cursor_]):
    node: Node_
    cursor: Cursor_

    @wrap_generic_init_subclass
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        type_name(graphql=edge_name)(cls)


@type_name(graphql=lambda *_: "PageInfo")
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


def connection_name(tp: Type["Connection"], *args) -> str:
    for base in generic_mro(tp[tuple(args)] if args else tp):  # type: ignore
        if get_origin(base) == Connection:
            return f"{get_node_name(get_args(base)[0])}Connection"
    raise NotImplementedError


Edge_ = TypeVar("Edge_", bound=Edge)


@type_name(graphql=connection_name)
@dataclass
class Connection(Generic[Node_, Cursor_, Edge_]):
    edges: Optional[Sequence[Optional[Edge_]]]
    page_info: PageInfo[Cursor_]

    @wrap_generic_init_subclass
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        type_name(graphql=connection_name)(cls)
