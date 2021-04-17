import collections.abc
from dataclasses import dataclass, fields
from typing import (
    Any,
    Callable,
    Collection,
    Container,
    Dict,
    Iterable,
    List,
    NewType,
    Optional,
    TYPE_CHECKING,
    Tuple,
    Type,
    Union,
)

from apischema.conversions.utils import (
    Converter,
    T as IdentityT,
    converter_types,
    identity,
)
from apischema.dataclasses import replace
from apischema.types import AnyType, COLLECTION_TYPES, MAPPING_TYPES
from apischema.typing import generic_mro, get_args
from apischema.utils import (
    get_origin_or_type,
    is_method,
    is_type_var,
    method_class,
    method_wrapper,
    substitute_type_vars,
)

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coercion


@dataclass(frozen=True)
class Conversion:
    converter: Union[Converter, property]
    source: AnyType = None
    target: AnyType = None
    sub_conversions: Optional["Conversions"] = None
    additional_properties: Optional[bool] = None
    coercion: Optional["Coercion"] = None
    default_fallback: Optional[bool] = None
    exclude_unset: Optional[bool] = None
    inherited: Optional[bool] = None

    def __post_init__(self):
        object.__setattr__(
            self, "sub_conversions", to_hashable_conversions(self.sub_conversions)
        )
        # Cannot use astuple because of deepcopy bug with property in py36
        cached_hash = hash(tuple(getattr(self, f.name) for f in fields(self)))
        object.__setattr__(self, "_hash", cached_hash)

    def __hash__(self):
        return self._hash  # type: ignore

    def __call__(self, *args, **kwargs):
        return self.converter(*args, **kwargs)


@dataclass(frozen=True)
class LazyConversion:
    get: Callable[[], Optional["Conversions"]]


ConvOrFunc = Union[Conversion, Converter, property, LazyConversion]
Conversions = Union[ConvOrFunc, Collection[ConvOrFunc]]
HashableConversions = Union[ConvOrFunc, Tuple[ConvOrFunc, ...]]


def to_hashable_conversions(
    conversions: Optional[Conversions],
) -> Optional[HashableConversions]:
    return tuple(conversions) if isinstance(conversions, Collection) else conversions


ResolvedConversion = NewType("ResolvedConversion", Conversion)
ResolvedConversions = Tuple[ResolvedConversion, ...]  # Tuple in order to be hashable


def resolve_conversion(
    conversion: Union[Converter, property, Conversion], namespace: Dict[str, Any] = None
) -> ResolvedConversion:
    if not isinstance(conversion, Conversion):
        conversion = Conversion(conversion)
    if is_method(conversion.converter):
        if conversion.source is None:
            conversion = replace(conversion, source=method_class(conversion.converter))
        conversion = replace(conversion, converter=method_wrapper(conversion.converter))
    assert not isinstance(conversion.converter, property)
    source, target = converter_types(
        conversion.converter, conversion.source, conversion.target, namespace
    )
    return ResolvedConversion(replace(conversion, source=source, target=target))


def resolve_conversions(conversions: Optional[Conversions]) -> ResolvedConversions:
    if not conversions:
        return ()
    result: List[ResolvedConversion] = []
    for conv in conversions if isinstance(conversions, Collection) else [conversions]:
        if isinstance(conv, LazyConversion):
            result.extend(resolve_conversions(conv.get()))  # type: ignore
        else:
            result.append(resolve_conversion(conv))
    return tuple(result)


def handle_identity_conversion(
    conversion: ResolvedConversion, cls: Type
) -> ResolvedConversion:
    if is_identity(conversion) and conversion.source == IdentityT:
        return ResolvedConversion(replace(conversion, source=cls, target=cls))
    else:
        return conversion


def is_identity(conversion: ResolvedConversion) -> bool:
    return (
        conversion.converter == identity
        and conversion.source == conversion.target
        and conversion.sub_conversions is None
        and conversion.additional_properties is None
        and conversion.coercion is None
        and conversion.default_fallback is None
        and conversion.exclude_unset is None
    )


ITERABLE_TYPES = (
    COLLECTION_TYPES.keys()
    | MAPPING_TYPES.keys()
    | {Iterable, collections.abc.Iterable, Container, collections.abc.Container}
)


def update_generics(
    conversion: ResolvedConversion,
    tp: AnyType,
    as_source: bool = False,
    as_target: bool = False,
) -> ResolvedConversion:

    assert as_source != as_target
    if as_source:
        subtype, supertype = tp, conversion.source
    elif as_target:
        subtype, supertype = conversion.target, tp
    else:
        raise NotImplementedError
    super_origin = get_origin_or_type(supertype)
    if getattr(subtype, "__parameters__", ()):
        subtype = subtype[subtype.__parameters__]
    if getattr(supertype, "__parameters__", ()):
        supertype = supertype[supertype.__parameters__]
    substitution = {}
    for base in generic_mro(subtype):
        base_origin = get_origin_or_type(base)
        if base_origin == super_origin or (
            base_origin in ITERABLE_TYPES and super_origin in ITERABLE_TYPES
        ):
            for base_arg, super_arg in zip(get_args(base), get_args(supertype)):
                if as_source and is_type_var(super_arg):
                    substitution[super_arg] = base_arg
                elif as_target and is_type_var(base_arg):
                    substitution[base_arg] = super_arg
            break
    if as_source:
        return ResolvedConversion(
            replace(
                conversion,
                source=tp,
                target=substitute_type_vars(conversion.target, substitution),
            )
        )
    elif as_target:
        return ResolvedConversion(
            replace(
                conversion,
                source=substitute_type_vars(conversion.source, substitution),
                target=tp,
            )
        )
    else:
        raise NotImplementedError
