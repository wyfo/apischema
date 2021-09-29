__all__ = ["Tagged", "TaggedUnion", "get_tagged"]

import warnings
from dataclasses import InitVar, dataclass, field
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

from apischema.aliases import alias as alias_metadata
from apischema.conversions.conversions import ConvOrFunc
from apischema.metadata import conversion
from apischema.metadata.keys import (
    DEFAULT_AS_SET_METADATA,
    FALL_BACK_ON_DEFAULT_METADATA,
    FLATTEN_METADATA,
    INIT_VAR_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SKIP_METADATA,
)
from apischema.schemas import Schema, schema
from apischema.types import Metadata, MetadataImplem, Undefined, UndefinedType
from apischema.typing import get_type_hints
from apischema.utils import PREFIX, get_args2, get_origin2, wrap_generic_init_subclass

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


INVALID_METADATA = {
    DEFAULT_AS_SET_METADATA,
    FALL_BACK_ON_DEFAULT_METADATA,
    INIT_VAR_METADATA,
    FLATTEN_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SKIP_METADATA,
}


@dataclass(frozen=True)
class Tagged(Generic[V]):
    metadata: Metadata = field(default_factory=MetadataImplem)
    alias: InitVar[Optional[str]] = None
    schema: InitVar[Optional[Schema]] = None
    deserialization: InitVar[Optional[ConvOrFunc]] = None
    serialization: InitVar[Optional[ConvOrFunc]] = None

    def __post_init__(
        self,
        alias: Optional[str],
        schema: Optional[Schema],
        deserialization: Optional[ConvOrFunc],
        serialization: Optional[ConvOrFunc],
    ):
        if self.metadata is None or isinstance(self.metadata, str):
            raise TypeError(
                "Tagged alias parameter is deprecated, use metadata instead"
            )
        if any(m is not None for m in (alias, schema, deserialization, serialization)):
            metadata = self.metadata
            warnings.warn(
                "Tagged keyword parameters are deprecated,"
                " use metadata parameter instead",
                DeprecationWarning,
            )
            if alias is not None:
                metadata |= alias_metadata(alias)
            if schema is not None:
                metadata |= schema
            if deserialization is not None or serialization is not None:
                metadata |= conversion(deserialization, serialization)
            object.__setattr__(self, "metadata", metadata)
        if self.metadata.keys() & INVALID_METADATA:
            raise TypeError("Invalid metadata in a TaggedUnion field")

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
            raise ValueError("TaggedUnion constructor expects only one field")
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

    @wrap_generic_init_subclass
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        tags = set(getattr(cls, TAGS_ATTR, ()))
        types = get_type_hints(cls, include_extras=True)
        for tag, tp in types.items():
            if get_origin2(tp) == Tagged:
                tagged = cls.__dict__.get(tag, Tagged())
                setattr(cls, tag, field(default=Undefined, metadata=tagged.metadata))
                cls.__annotations__[tag] = Union[
                    get_args2(types[tag])[0], UndefinedType
                ]
                tags.add(tag)
            elif tag not in tags:
                if get_origin2(tp) != ClassVar:
                    cls.__annotations__[tag] = ClassVar[tp]
                else:
                    raise TypeError(
                        "Only Tagged or ClassVar fields are allowed in TaggedUnion"
                    )
        setattr(cls, TAGS_ATTR, tags)
        schema(min_props=1, max_props=1)(dataclass(init=False, repr=False)(cls))
        for tag in tags:
            setattr(cls, tag, Tag(tag, cls))


def get_tagged(tagged_union: TaggedUnion) -> Tuple[str, Any]:
    defined = {
        tag: getattr(tagged_union, tag)
        for tag in getattr(tagged_union, TAGS_ATTR)
        if getattr(tagged_union, tag) is not Undefined
    }
    return next(iter(defined.items()))
