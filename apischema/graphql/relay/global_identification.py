import sys
from abc import ABC, abstractmethod
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
from dataclasses import Field, _FIELDS, dataclass, field  # type: ignore

from apischema import deserialize, deserializer, serialize, serializer
from apischema.graphql import interface
from apischema.graphql.schema import ID
from apischema.json_schema.refs import get_ref
from apischema.metadata import conversion
from apischema.types import AnyType
from apischema.typing import generic_mro, get_args, get_origin
from apischema.utils import has_type_vars

Id = TypeVar("Id")


class InvalidGlobalId(Exception):
    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return f"{self.value} is not a valid id"


class NotANode(Exception):
    def __init__(self, node_class: str):
        self.node_class = node_class

    def __str__(self):
        return f"{self.node_class} is not a Node"


Node_ = TypeVar("Node_", bound="Node")


@dataclass
class GlobalId(Generic[Node_]):
    id: str
    node_class: Type[Node_]

    @staticmethod
    def deserialize(global_id: ID) -> "GlobalId":
        try:
            node_class, id = global_id.split(":")
        except ValueError:
            raise InvalidGlobalId(global_id)
        if node_class not in _nodes:
            raise NotANode(node_class)
        return GlobalId(id, _nodes[node_class])

    def serialize(self) -> ID:
        return ID(f"{self.node_class._node_key()}:{self.id}")


deserializer(GlobalId.deserialize)
serializer(GlobalId.serialize)


# Use fake conversion to give the id field an ID type for Node (unspecialized) class
def _fake_serializer(_) -> GlobalId:
    raise NotImplementedError


N = TypeVar("N", bound="Node")


@interface
@dataclass  # type: ignore
class Node(Generic[Id], ABC):
    _id_type: ClassVar[AnyType]  # set in __init_subclass__
    id: Id = field(metadata=conversion(serialization=_fake_serializer))

    @classmethod
    def id_from_global(cls: Type[N], global_id: GlobalId[N]) -> Id:
        # Use coercion to handle integer id
        return cast(Id, deserialize(cls._id_type, global_id.id, coercion=True))

    @classmethod
    def id_to_global(cls: Type[N], id: Id) -> GlobalId[N]:
        return GlobalId(str(serialize(id)), cls)

    @property
    def global_id(self: N) -> GlobalId[N]:
        return self.id_to_global(self.id)

    @classmethod
    def get_by_global_id(
        cls: Type[N], global_id: GlobalId, info: graphql.GraphQLResolveInfo = None
    ) -> Union[N, Awaitable[N]]:
        if global_id.node_class != cls:
            raise ValueError(
                f"Expected {cls.__name__} id, found {global_id.node_class.__name__} id"
            )
        return cls.get_by_id(cls.id_from_global(global_id), info)

    @classmethod
    @abstractmethod
    def get_by_id(
        cls: Type[N], id: Id, info: graphql.GraphQLResolveInfo = None
    ) -> Union[N, Awaitable[N]]:
        raise NotImplementedError

    @classmethod
    def _node_key(cls) -> str:
        node_name = get_ref(cls)
        if node_name is None:
            raise TypeError(f"Node {cls} has no schema_ref registered")
        return node_name

    def __init_subclass__(cls, abstract: bool = False, **kwargs):
        super().__init_subclass__(**kwargs)  # type: ignore
        if abstract:
            return
        if sys.version_info >= (3, 7):
            if not has_type_vars(cls) and cls.get_by_id is not Node.get_by_id:
                _set_id_type(cls)
                _tmp_nodes.append(cls)
        else:
            if cls not in _tmp_nodes:
                _tmp_nodes.append(cls)


def _set_id_type(cls):
    for base in cls.__mro__:
        if base != Node and Node.get_by_id.__name__ in base.__dict__:
            if not isinstance(
                base.__dict__[base.get_by_id.__name__], (classmethod, staticmethod)
            ):
                raise TypeError(
                    f"{cls.__name__}.get_by_id must be a classmethod/staticmethod"
                )
            break
    else:
        raise TypeError(f"{cls.__name__}.{Node.get_by_id.__name__} must be defined")
    for base in generic_mro(cls):
        if get_origin(base) == Node:
            (_id_type,) = get_args(base)
            break
    else:
        raise NotImplementedError

    def serialize_id(id) -> GlobalId:
        return GlobalId(serialize(id), cls)

    id_field = cast(Field, getattr(cls, _FIELDS)["id"])
    cls.id = Field(  # type: ignore
        id_field.default,
        id_field.default_factory,  # type: ignore
        id_field.init,
        id_field.repr,
        id_field.hash,
        id_field.compare,
        id_field.metadata | conversion(serialization=serialize_id),
    )
    cls.__annotations__["id"] = _id_type
    cls._id_type = _id_type


# Use dict instead of set in order to keep order (because 3.6 generate duplicates)
_tmp_nodes: List[Type[Node]] = []
_nodes: Dict[str, Type[Node]] = {}


if sys.version_info < (3, 7):

    def nodes() -> Collection[Type[Node]]:
        for node_cls in _tmp_nodes:
            if (
                has_type_vars(node_cls)
                or get_args(node_cls)
                or node_cls.get_by_id is Node.get_by_id
            ):
                continue
            _set_id_type(node_cls)
            _nodes[node_cls._node_key()] = dataclass(node_cls)
        return list(_nodes.values())


else:

    def nodes() -> Collection[Type[Node]]:
        for node_cls in _tmp_nodes:
            _nodes[node_cls._node_key()] = node_cls
        return list(_nodes.values())


def node(id: GlobalId, info: graphql.GraphQLResolveInfo = None) -> Node:
    return id.node_class.get_by_global_id(id, info)
