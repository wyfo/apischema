__all__ = ["Tagged", "TaggedUnion", "get_tagged"]
from dataclasses import dataclass, field
from typing import (
    Any,
    ClassVar,
    Generic,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from apischema.aliases import alias
from apischema.conversions.conversions import ConvOrFunc
from apischema.json_schema.schema import Schema
from apischema.metadata import conversion
from apischema.types import Metadata, MetadataImplem
from apischema.typing import get_type_hints
from apischema.utils import PREFIX, Undefined, UndefinedType, get_args2, get_origin2

TAGS_ATTR = f"{PREFIX}tags"

T = TypeVar("T", bound="TaggedUnion")
V = TypeVar("V")


class Tag(str, Generic[T, V]):
    def __new__(cls, tag: str, type: Type[T]):
        return super().__new__(cls, tag)

    def __init__(self, tag: str, type: Type[T]):
        super().__init__()
        self.type = type

    def __call__(self, value: V) -> T:
        return self.type(**{self: value})  # type: ignore


@dataclass(frozen=True)
class Tagged(Generic[V]):
    alias: Optional[str] = None
    schema: Optional[Schema] = None
    deserialization: Optional[ConvOrFunc] = None
    serialization: Optional[ConvOrFunc] = None

    @property
    def metadata(self) -> Metadata:
        metadata: Metadata = MetadataImplem()
        if self.alias is not None:
            metadata |= alias(self.alias)
        if self.schema is not None:
            metadata |= self.schema
        if self.deserialization is not None or self.serialization is not None:
            metadata |= conversion(self.deserialization, self.serialization)
        return metadata

    @overload
    def __get__(self, instance: None, owner: Type[T]) -> Tag[T, V]:
        ...

    @overload
    def __get__(self, instance: Any, owner) -> Union[V, UndefinedType]:
        ...

    def __get__(self, instance, owner):
        raise NotImplementedError


class TaggedUnion:
    def __init__(self, **kwargs):
        if len(kwargs) != 1:
            raise ValueError(
                f"tagged union must have one and only one tag set,"
                f" found {list(kwargs)}"
            )
        tags = getattr(self, TAGS_ATTR)
        for tag in tags:
            setattr(self, tag, Undefined)
        for tag, value in kwargs.items():
            if tag not in tags:
                raise TypeError(f"{type(self)} has no tag {tag}")
            setattr(self, tag, value)

    def __repr__(self):
        tag, value = get_tagged(self)
        return f"{type(self).__name__}({tag}={value!r})"

    def __init_subclass__(cls, **kwargs):
        tags = set(getattr(cls, TAGS_ATTR, ()))
        types = get_type_hints(cls, include_extras=True)
        for tag, tp in types.items():
            if get_origin2(tp) == Tagged:
                if tag in tags:
                    raise TypeError(f"Cannot redefine tag {tag} in {cls}")
                tagged = cls.__dict__.get(tag, Tagged())
                setattr(cls, tag, field(default=Undefined, metadata=tagged.metadata))
                cls.__annotations__[tag] = Union[
                    get_args2(types[tag])[0], UndefinedType
                ]
                tags.add(tag)
            elif tag not in tags and get_origin2(tp) != ClassVar:
                cls.__annotations__[tag] = ClassVar[tp]
        setattr(cls, TAGS_ATTR, tags)
        dataclass(init=False, repr=False)(cls)
        for tag in tags:
            setattr(cls, tag, Tag(tag, cls))


def get_tagged(tagged_union: TaggedUnion) -> Tuple[str, Any]:
    defined = {
        tag: getattr(tagged_union, tag)
        for tag in getattr(tagged_union, TAGS_ATTR)
        if getattr(tagged_union, tag) is not Undefined
    }
    return next(iter(defined.items()))
