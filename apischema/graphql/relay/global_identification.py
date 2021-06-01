from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Awaitable,
    ClassVar,
    Collection,
    Dict,
    Generic,
    List,
    Type,
    TypeVar,
    Union,
    cast,
)

import graphql

from apischema import deserialize, deserializer, serialize, serializer, type_name
from apischema.graphql import ID, interface, resolver
from apischema.metadata import skip
from apischema.type_names import get_type_name
from apischema.typing import generic_mro, get_args, get_origin
from apischema.utils import PREFIX, has_type_vars, wrap_generic_init_subclass

ID_TYPE_ATTR = f"{PREFIX}id_type"


class InvalidGlobalId(Exception):
    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return f"{self.value} is not a valid global id"


class NotANode(Exception):
    def __init__(self, node_type: str):
        self.node_type = node_type

    def __str__(self):
        return f"{self.node_type} is not a Node"


Node_ = TypeVar("Node_", bound="Node")


@dataclass
class GlobalId(Generic[Node_]):
    id: str
    node_type: Type[Node_]


@deserializer
def deserialize_global_id(global_id: ID) -> GlobalId:
    try:
        node_key, id = global_id.split(":")
    except ValueError:
        raise InvalidGlobalId(global_id) from None
    try:
        return GlobalId(id, _nodes[node_key])
    except KeyError:
        raise NotANode(node_key) from None


@serializer
def serialize_global_id(global_id: GlobalId) -> ID:
    return ID(f"{global_id.node_type._node_key()}:{global_id.id}")


Id = TypeVar("Id")


@type_name(graphql=lambda *_: "Node")
@interface
@dataclass  # type: ignore
class Node(Generic[Id], ABC):
    id: Id = field(metadata=skip)
    global_id: ClassVar[property]

    @property  # type: ignore
    def global_id(self: Node_) -> GlobalId[Node_]:
        return self.id_to_global(self.id)

    @classmethod
    def id_from_global(cls: Type[Node_], global_id: GlobalId[Node_]) -> Id:
        if global_id.node_type != cls:
            raise ValueError(
                f"Expected {cls.__name__} global id,"
                f" found {global_id.node_type.__name__} global id"
            )
        id_type = getattr(cls, ID_TYPE_ATTR)
        # Use coercion to handle integer id
        return cast(Id, deserialize(id_type, global_id.id, coerce=True))

    @classmethod
    def id_to_global(cls: Type[Node_], id: Id) -> GlobalId[Node_]:
        return GlobalId(str(serialize(getattr(cls, ID_TYPE_ATTR), id)), cls)

    @classmethod
    @abstractmethod
    def get_by_id(
        cls: Type[Node_], id: Id, info: graphql.GraphQLResolveInfo = None
    ) -> Union[Node_, Awaitable[Node_]]:
        raise NotImplementedError

    @classmethod
    def _node_key(cls) -> str:
        node_name = get_type_name(cls).graphql
        if node_name is None:
            raise TypeError(f"Node {cls} has no type_name registered")
        return node_name

    @wrap_generic_init_subclass
    def __init_subclass__(cls, not_a_node: bool = False, **kwargs):
        super().__init_subclass__(**kwargs)  # type: ignore
        if not not_a_node:
            _tmp_nodes.append(cls)


resolver(alias="id")(Node.global_id)  # cannot directly decorate property because py36

_tmp_nodes: List[Type[Node]] = []
_nodes: Dict[str, Type[Node]] = {}


def process_node(node_cls: Type[Node]):
    if has_type_vars(node_cls) or node_cls.get_by_id is Node.get_by_id:
        return
    for base in node_cls.__mro__:
        if base != Node and Node.get_by_id.__name__ in base.__dict__:
            if not isinstance(
                base.__dict__[Node.get_by_id.__name__], (classmethod, staticmethod)
            ):
                raise TypeError(
                    f"{node_cls.__name__}.get_by_id must be a"
                    f" classmethod/staticmethod"
                )
            break
    for base in generic_mro(node_cls):
        if get_origin(base) == Node:
            setattr(node_cls, ID_TYPE_ATTR, get_args(base)[0])
            _nodes[node_cls._node_key()] = node_cls
            break
    else:
        raise TypeError("Node type parameter Id must be specialized")


def nodes() -> Collection[Type[Node]]:
    for node_cls in _tmp_nodes:
        process_node(node_cls)
    return list(_nodes.values())


def node(id: ID, info: graphql.GraphQLResolveInfo = None) -> Node:
    global_id = deserialize_global_id(id)
    node_type = global_id.node_type
    return node_type.get_by_id(node_type.id_from_global(global_id), info)
