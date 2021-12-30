import operator
import sys
from dataclasses import dataclass
from functools import reduce
from typing import (
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    TypeVar,
    Union,
)

from apischema.cache import CacheAwareDict
from apischema.conversions import Conversion, deserializer, serializer
from apischema.metadata.keys import DISCRIMINATOR_METADATA
from apischema.objects import object_fields
from apischema.type_names import get_type_name
from apischema.types import AnyType, MetadataMixin
from apischema.typing import get_args, is_literal, is_typed_dict
from apischema.utils import get_origin_or_type2, identity, no_annotated

try:
    from apischema.typing import Literal
except ImportError:
    Literal = ...  # type: ignore

Cls = TypeVar("Cls", bound=type)


def get_discriminated(alias: str, tp: AnyType) -> Sequence[str]:
    cls = get_origin_or_type2(tp)
    try:
        has_field = False
        for field in object_fields(cls).values():
            if field.alias == alias:
                has_field = True
                field_type = no_annotated(field.type)
                if is_literal(field_type):
                    if sys.version_info < (3, 7):  # py36
                        literal_args = field_type.__values__
                    else:
                        literal_args = get_args(field_type)
                    return [v for v in literal_args if isinstance(v, str)]
        if (
            is_typed_dict(cls) and not has_field
        ):  # TypedDict must have a discriminator field
            return ()
        return [name for name in [get_type_name(tp).json_schema] if name is not None]
    except TypeError:
        return ()


def default_discriminator_mapping(
    alias: str, types: Sequence[AnyType]
) -> Mapping[str, AnyType]:
    mapping = {}
    for tp in types:
        discriminated = get_discriminated(alias, tp)
        if not discriminated:
            raise TypeError(f"{tp} can't be discriminated")
        for key in discriminated:
            mapping[key] = tp
    return mapping


def rec_subclasses(cls: type) -> Iterable[type]:
    for sub_cls in cls.__subclasses__():
        yield sub_cls
        yield from rec_subclasses(sub_cls)


@dataclass(frozen=True, unsafe_hash=False)
class Discriminator(MetadataMixin):
    key = DISCRIMINATOR_METADATA
    alias: str
    mapping: Union[
        Mapping[str, AnyType], Callable[[str, Sequence[AnyType]], Mapping[str, AnyType]]
    ] = default_discriminator_mapping
    override_implicit: bool = True

    def get_mapping(self, types: Sequence[AnyType]) -> Mapping[str, AnyType]:
        default_mapping = default_discriminator_mapping(self.alias, types)
        if self.mapping is default_discriminator_mapping:
            return default_mapping
        mapping = (
            self.mapping(self.alias, types) if callable(self.mapping) else self.mapping
        )
        if self.override_implicit:
            mapping_types = set(mapping.values())
            mapping = dict(mapping)
            for key, tp in default_mapping.items():
                if tp not in mapping_types:
                    mapping[key] = tp
            return mapping
        else:
            return {**default_mapping, **mapping}

    # Make it hashable to be used in Annotated
    def __hash__(self):
        return hash(id(self))

    def __call__(self, cls: Cls) -> Cls:
        _discriminators[cls] = self
        deserializer(
            lazy=lambda: Conversion(
                identity, source=Union[tuple(rec_subclasses(cls))], target=cls
            ),
            target=cls,
        )
        serializer(
            lazy=lambda: Conversion(
                identity,
                source=cls,
                target=Union[tuple(rec_subclasses(cls))],
                inherited=False,
            ),
            source=cls,
        )
        return cls


_discriminators: MutableMapping[type, Discriminator] = CacheAwareDict({})
get_discriminator = _discriminators.get


discriminator = Discriminator


def get_discriminated_parent(cls: type) -> Optional[type]:
    for base in cls.__mro__:
        if base in _discriminators:
            return base
    return None


def get_inherited_discriminator(types: Iterable[AnyType]) -> Optional[Discriminator]:
    discriminators = [
        {
            base
            for base in getattr(get_origin_or_type2(tp), "__mro__", ())
            if base in _discriminators
        }
        for tp in types
    ]
    for cls in reduce(operator.and_, discriminators):
        return _discriminators[cls]
    return None
