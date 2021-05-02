__all__ = [
    "ClientMutationId",
    "Connection",
    "Edge",
    "GlobalId",
    "Mutation",
    "Node",
    "PageInfo",
    "base64_encoding",
    "mutations",
    "node",
    "nodes",
]
from .connections import Connection, Edge, PageInfo
from .global_identification import GlobalId, Node, node, nodes
from .mutations import ClientMutationId, Mutation, mutations
from .utils import base64_encoding


def alter_default_type_name():
    from apischema import settings
    from apischema.graphql.relay.connections import Connection, Edge, PageInfo
    from apischema.graphql.relay.global_identification import Node
    from apischema.type_names import get_type_name
    from apischema.types import NoneType
    from apischema.typing import generic_mro, get_args, get_origin
    from apischema.utils import (
        get_args2,
        get_origin_or_type,
        has_type_vars,
        is_union_of,
    )

    _set_default_type_name = settings.default_type_name
    _origin_default_type_name = settings.default_type_name()

    def get_node_name(tp):
        if is_union_of(tp, NoneType) and len(get_args2(tp)):
            tp = next(arg for arg in get_args2(tp) if arg is not NoneType)
        ref = get_type_name(tp).graphql
        if ref is None:
            raise TypeError(
                f"Node {tp} must have a ref registered to be used with connection"
            )
        return ref

    def _default_type_name(func=None):
        nonlocal _origin_default_type_name
        if func is None:
            return _origin_default_type_name
        else:
            _origin_default_type_name = func

            def wrapper(tp):
                cls = get_origin_or_type(tp)
                if (
                    isinstance(cls, type)
                    and issubclass(cls, (Connection, Edge, PageInfo))
                    and not has_type_vars(tp)
                ):
                    for base in generic_mro(tp):
                        if get_origin(base) == Connection:
                            return f"{get_node_name(get_args(base)[0])}Connection"
                        if get_origin(base) == Edge:
                            return f"{get_node_name(get_args(base)[0])}Edge"
                        if get_origin(base) == PageInfo:
                            return "PageInfo"
                elif cls == Node:
                    return "Node"
                else:
                    return func(tp)

            _set_default_type_name(wrapper)

    settings.default_type_name = _default_type_name
    _default_type_name(_origin_default_type_name)


alter_default_type_name()
del alter_default_type_name
