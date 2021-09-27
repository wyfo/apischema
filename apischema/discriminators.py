import operator
from dataclasses import dataclass
from functools import reduce
from typing import (
    Callable,
    Dict,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from apischema.cache import CacheAwareDict
from apischema.metadata.keys import DISCRIMINATOR_METADATA
from apischema.type_names import get_type_name
from apischema.types import AnyType, MetadataMixin
from apischema.typing import get_args, is_union
from apischema.utils import get_args2, get_origin2

if TYPE_CHECKING:
    from apischema.objects import ObjectField

try:
    from apischema.typing import Literal
except ImportError:
    Literal = ...  # type: ignore

Cls = TypeVar("Cls", bound=type)


@dataclass(frozen=True, unsafe_hash=False)
class UnionDiscriminator(MetadataMixin):
    key = DISCRIMINATOR_METADATA
    property_name: str
    mapping: Optional[Mapping[str, AnyType]]

    # Make it hashable to be used in Annotated
    def __hash__(self):
        return hash(id(self))

    def __call__(self, cls: Cls) -> Cls:
        _discriminators[cls] = self
        return cls


_discriminators: MutableMapping[type, UnionDiscriminator] = CacheAwareDict({})
get_discriminator = _discriminators.get


class Discriminator(MetadataMixin):
    key = DISCRIMINATOR_METADATA

    def __call__(
        self, property_name: str, mapping: Optional[Mapping[str, AnyType]] = None
    ) -> UnionDiscriminator:
        return UnionDiscriminator(property_name, mapping)


discriminator = Discriminator()


def discriminator_fields(
    types: Sequence[AnyType], filtr: Callable[["ObjectField"], bool]
) -> Optional[Sequence[Optional["ObjectField"]]]:
    from apischema.objects import object_fields

    result = []
    for tp in types:
        if get_type_name(tp).json_schema is None:
            return None
        try:
            fields = object_fields(tp).values()
        except TypeError:
            return None
        result.append(next(filter(filtr, fields), None))  # type: ignore
    return result


def field_discriminators(field: "ObjectField") -> Sequence[str]:
    if get_origin2(field.type) is Literal:
        return [val for val in get_args2(field.type) if isinstance(val, str)]
    elif field.default_factory is not None and isinstance(field.default_factory(), str):
        return [field.default_factory()]
    else:
        return []


def _discriminate_field(
    mapping: Dict[str, AnyType], tp: AnyType, field: "ObjectField"
) -> bool:
    if get_origin2(field.type) is Literal:
        mapping.update((v, tp) for v in get_args2(field.type))
    elif field.default_factory is not None and isinstance(field.default_factory(), str):
        mapping[field.default_factory()] = tp
    else:
        type_name = get_type_name(tp).json_schema
        if type_name is None:
            return False
        mapping[type_name] = tp
    return True


def discriminate_union(
    union: AnyType,
    has_conversion: Callable[[AnyType], bool],
    discriminator: UnionDiscriminator,
) -> Tuple[str, Mapping[str, AnyType]]:
    error = TypeError("Only union of object types can be discriminated")
    if not is_union(union):
        raise error
    types = get_args(union)
    if any(map(has_conversion, types)):
        raise error
    fields = discriminator_fields(
        types, lambda f: f.alias == discriminator.property_name
    )
    if fields is None:
        raise error
    mapping = dict(discriminator.mapping) if discriminator.mapping is not None else {}
    for tp, field in zip(types, fields):
        if tp not in mapping.values():
            if field is None:
                raise TypeError(
                    f"Discriminated {tp} has no field {discriminator.property_name}"
                )
            if not _discriminate_field(mapping, tp, field):
                raise TypeError(
                    f"Discriminated {tp} has no type_name to be discriminated against"
                )
    return discriminator.property_name, mapping


def inherited_discriminator(*types: AnyType) -> Optional[type]:
    discriminators = [
        {base for base in getattr(tp, "__mro__", ()) if base in _discriminators}
        for tp in types
    ]
    if any(len(d) > 1 for d in discriminators):
        raise TypeError("Multiple discriminator base")
    return next(iter(reduce(operator.and_, discriminators)), None)


def discriminate_types(
    types: Sequence[AnyType], has_conversion: Callable[[AnyType], bool]
) -> Optional[Tuple[str, Mapping[str, AnyType]]]:
    if any(map(has_conversion, types)):
        return None
    inherited = inherited_discriminator(*types)
    if inherited is not None:
        try:
            return discriminate_union(
                Union[tuple(types)], has_conversion, _discriminators[inherited]  # type: ignore
            )
        except TypeError:
            return None
    fields = discriminator_fields(types, lambda f: f.discriminator)
    if fields is None or not all(fields):
        return None
    mapping: Dict[str, AnyType] = {}
    property_name = cast(ObjectField, fields[0]).alias
    for tp, field in zip(types, fields):
        assert field is not None
        if field.alias != property_name or not _discriminate_field(mapping, tp, field):
            return None
    return property_name, mapping
