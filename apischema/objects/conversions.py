from dataclasses import replace
from types import new_class
from typing import (
    Callable,
    Generic,
    Iterable,
    NamedTuple,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Type,
    TypeVar,
    Union,
)

from apischema.conversions.conversions import Conversion
from apischema.conversions.converters import deserializer, serializer
from apischema.conversions.utils import identity
from apischema.objects.fields import ObjectField
from apischema.utils import with_parameters

if TYPE_CHECKING:
    from apischema.deserialization import Coercion

T = TypeVar("T")


class ObjectWrapper(Generic[T]):
    type: Type[T]
    fields: Sequence[ObjectField]


class DeserializationSerialization(NamedTuple):
    deserialization: Conversion
    serialization: Conversion


def object_conversion(
    cls: type,
    fields: Iterable[ObjectField],
    *,
    additional_properties: Optional[bool] = None,
    coercion: Optional["Coercion"] = None,
    default_fallback: Optional[bool] = None,
    exclude_unset: Optional[bool] = None,
) -> DeserializationSerialization:
    wrapper = new_class(
        f"{cls.__name__}{ObjectWrapper.__name__}",
        (ObjectWrapper[T],),
        exec_body=lambda ns: ns.update({"type": cls, "fields": tuple(fields)}),
    )
    conv = Conversion(
        identity,
        additional_properties=additional_properties,
        coercion=coercion,
        default_fallback=default_fallback,
        exclude_unset=exclude_unset,
    )
    tp = with_parameters(cls)
    return DeserializationSerialization(
        replace(conv, source=wrapper[tp], target=tp),  # type: ignore
        replace(conv, source=tp, target=wrapper[tp]),  # type: ignore
    )


def as_object(
    cls: Type[T],
    fields: Union[Iterable[ObjectField], Callable[[], Iterable[ObjectField]]],
    *,
    additional_properties: Optional[bool] = None,
    coercion: Optional["Coercion"] = None,
    default_fallback: Optional[bool] = None,
    exclude_unset: Optional[bool] = None,
) -> None:
    def get_conversions(fields: Iterable[ObjectField]) -> DeserializationSerialization:
        return object_conversion(
            cls,
            fields,
            additional_properties=additional_properties,
            coercion=coercion,
            default_fallback=default_fallback,
            exclude_unset=exclude_unset,
        )

    if callable(fields):
        deser = None

        def compute_deser() -> DeserializationSerialization:
            nonlocal deser
            if deser is None:
                deser = get_conversions(fields())  # type: ignore
            return deser

        deserializer(lazy=lambda: compute_deser().deserialization, target=cls)
        serializer(lazy=lambda: compute_deser().serialization, source=cls)
    else:
        d_conv, s_conv = get_conversions(fields)  # type: ignore
        deserializer(d_conv)
        serializer(s_conv)
