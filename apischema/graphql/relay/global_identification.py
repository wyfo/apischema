from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    ClassVar,
    Generic,
    List,
    NamedTuple,
    Type,
    TypeVar,
    Union,
)

import graphql

from apischema.cache import cache
from apischema.conversions import deserializer, serializer
from apischema.deserialization import deserialize
from apischema.graphql import ID, interface, resolver
from apischema.metadata import skip
from apischema.serialization import serialize
from apischema.type_names import get_type_name, type_name
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


class IdMethods(NamedTuple):
    deserialize: Callable[[Any], Any]
    serialize: Callable[[Any], Any]


@cache
def id_methods(cls: Type["Node"]) -> IdMethods:
    for base in generic_mro(cls):
        if get_origin(base) == Node:
            id_type = get_args(base)[0]
            return IdMethods(
                # Use coercion to handle integer id
                lambda id: deserialize(id_type, id, coercion=True),
                lambda id: serialize(id),
            )
    else:
        raise TypeError("Node type parameter Id must be specialized")


Id = TypeVar("Id")


@type_name(graphql=lambda *_: "Node")
@interface
@dataclass  # type: ignore
class Node(Generic[Id], ABC):
    id: Id = field(metadata=skip)
    global_id: ClassVar[property]

    @resolver(alias="id")  # type: ignore
    @property
    def global_id(self: Node_) -> GlobalId[Node_]:
        return self.id_to_global(self.id)

    @classmethod
    def id_from_global(cls: Type[Node_], global_id: GlobalId[Node_]) -> Id:
        if global_id.node_type != cls:
            raise ValueError(
                f"Expected {cls.__name__} global id,"
                f" found {global_id.node_type.__name__} global id"
            )
        deserialize, _ = id_methods(cls)
        return deserialize(global_id.id)

    @classmethod
    def id_to_global(cls: Type[Node_], id: Id) -> GlobalId[Node_]:
        _, serialize = id_methods(cls)
        return GlobalId(str(serialize(id)), cls)

    @classmethod
    @abstractmethod
    def get_by_id(
        cls: Type[Node_], id: Id, info: graphql.GraphQLResolveInfo
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
        if not_a_node:
            return
        if has_type_vars(cls) or cls.get_by_id is Node.get_by_id:
            return
        for base in cls.__mro__:
            if base != Node and Node.get_by_id.__name__ in base.__dict__:
                if not isinstance(
                    base.__dict__[Node.get_by_id.__name__], (classmethod, staticmethod)
                ):
                    raise TypeError(
                        f"{cls.__name__}.get_by_id must be a"
                        f" classmethod/staticmethod"
                    )
                break
        nodes.append(cls)


nodes: List[Type[Node]] = []


@cache
def node_cls_by_key(node_key: str) -> Type[Node]:
    for cls in nodes:
        if cls._node_key() == node_key:
            return cls
    raise NotANode(node_key)


@deserializer
def deserialize_global_id(global_id: ID) -> GlobalId:
    try:
        node_key, id = global_id.split(":")
    except ValueError:
        raise InvalidGlobalId(global_id) from None
    return GlobalId(id, node_cls_by_key(node_key))


@serializer
def serialize_global_id(global_id: GlobalId) -> ID:
    return ID(f"{global_id.node_type._node_key()}:{global_id.id}")


def node(id: ID, info: graphql.GraphQLResolveInfo) -> Node:
    global_id = deserialize_global_id(id)
    node_type = global_id.node_type
    return node_type.get_by_id(node_type.id_from_global(global_id), info)
