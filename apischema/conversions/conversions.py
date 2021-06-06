from dataclasses import dataclass
from functools import lru_cache
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    List,
    NewType,
    Optional,
    TYPE_CHECKING,
    Tuple,
    Union,
)

from apischema.conversions.utils import (
    Converter,
    T as IdentityT,
    converter_types,
    identity,
)
from apischema.dataclasses import replace
from apischema.types import AnyType
from apischema.utils import deprecate_kwargs, is_method, method_class, method_wrapper

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coerce


@deprecate_kwargs({"sub_conversions": "sub_conversion"})
@dataclass(frozen=True)
class Conversion:
    converter: Union[Converter, property]
    source: AnyType = None
    target: AnyType = None
    sub_conversion: Optional["AnyConversion"] = None
    additional_properties: Optional[bool] = None
    fall_back_on_any: Optional[bool] = None
    check_type: Optional[bool] = None
    coerce: Optional["Coerce"] = None
    fall_back_on_default: Optional[bool] = None
    exclude_unset: Optional[bool] = None
    inherited: Optional[bool] = None

    def __call__(self, *args, **kwargs):
        return self.converter(*args, **kwargs)


@dataclass(frozen=True)
class LazyConversion:
    get: Callable[[], Optional["AnyConversion"]]

    def __post_init__(self):
        object.__setattr__(self, "get", lru_cache(1)(self.get))

    @property
    def inherited(self) -> Optional[bool]:
        conversion = self.get()  # type: ignore
        return isinstance(conversion, Conversion) and conversion.inherited


ConvOrFunc = Union[Conversion, Converter, property, LazyConversion]
AnyConversion = Union[ConvOrFunc, Tuple[ConvOrFunc, ...]]
DefaultConversion = Callable[[AnyType], Optional[AnyConversion]]


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


def resolve_any_conversion(conversion: Optional[AnyConversion]) -> ResolvedConversions:
    if not conversion:
        return ()
    result: List[ResolvedConversion] = []
    for conv in conversion if isinstance(conversion, Collection) else [conversion]:
        if isinstance(conv, LazyConversion):
            result.extend(resolve_any_conversion(conv.get()))  # type: ignore
        else:
            result.append(resolve_conversion(conv))
    return tuple(result)


def handle_identity_conversion(
    conversion: ResolvedConversion, tp: AnyType
) -> ResolvedConversion:
    if is_identity(conversion) and conversion.source == IdentityT:
        return ResolvedConversion(replace(conversion, source=tp, target=tp))
    else:
        return conversion


def is_identity(conversion: ResolvedConversion) -> bool:
    return (
        conversion.converter == identity
        and conversion.source == conversion.target
        and conversion.sub_conversion is None
        and conversion.additional_properties is None
        and conversion.coerce is None
        and conversion.fall_back_on_default is None
        and conversion.exclude_unset is None
    )
