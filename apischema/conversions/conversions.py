from dataclasses import dataclass
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

from apischema.conversions.utils import Converter, converter_types, identity
from apischema.dataclasses import replace
from apischema.types import AnyType
from apischema.utils import get_origin_or_type, is_method, method_class, method_wrapper

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

    def __call__(self, *args, **kwargs):
        return self.converter(*args, **kwargs)


@dataclass(frozen=True)
class LazyConversion:
    get: Callable[[], Optional["Conversions"]]


ConvOrFunc = Union[Conversion, Converter, property, LazyConversion]
Conversions = Union[ConvOrFunc, Collection[ConvOrFunc]]

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


def handle_container_conversions(
    tp: AnyType,
    next_conversions: Optional[Conversions],
    prev_conversions: Optional[Conversions],
    dynamic: bool,
) -> Optional[Conversions]:
    origin = get_origin_or_type(tp)
    if (
        prev_conversions
        and not dynamic
        and (
            (isinstance(origin, type) and issubclass(origin, Collection))
            or origin == Union
        )
    ):
        if next_conversions:
            return (
                LazyConversion(lambda: next_conversions),
                LazyConversion(lambda: prev_conversions),
            )
        else:
            return prev_conversions
    else:
        return next_conversions
