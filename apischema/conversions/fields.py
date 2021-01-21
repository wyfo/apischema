from enum import Enum, auto

from apischema.conversions.conversions import (
    ConvOrFunc,
    Conversion,
    ResolvedConversion,
    handle_serialization_method,
)
from apischema.conversions.utils import converter_types
from apischema.dataclasses import replace
from apischema.types import AnyType
from apischema.typing import get_args, get_origin
from apischema.utils import get_args2, get_origin2, is_type_var, substitute_type_vars

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore


class Variance(Enum):
    COVARIANT = auto()
    CONTRAVARIANT = auto()


def handle_generic_field_type(
    field_type: AnyType, base: AnyType, other: AnyType, variance: Variance
) -> AnyType:
    """When conversion is generic, try to adapt the other side of the conversion
    depending on the field_type

    Args:
        field_type: type of the field
        base: side of the conversion where the field is
        other: other side of the conversion
        variance: variance of the conversion
    """
    if is_type_var(base):
        type_vars = {base: field_type}
    elif (
        # field_type is generic with free typevars, field_type also generic with
        # number of args, none of their args are generic (must be type or typevar)
        # and with
        get_origin2(base) is not None
        and getattr(base, "__parameters__", ())
        and len(get_args2(base)) == len(get_args2(field_type))
        and not any(map(get_origin2, get_args2(base)))
        and not any(map(get_origin2, get_args2(field_type)))
        and not any(
            not is_type_var(base_arg) and base_arg != field_arg
            for base_arg, field_arg in zip(get_args2(base), get_args2(field_type))
        )
    ):
        field_type_origin, base_origin = get_origin2(field_type), get_origin2(base)
        assert field_type_origin is not None and base_origin is not None
        if base_origin != field_type_origin:
            if variance == Variance.COVARIANT and not issubclass(
                base_origin, field_type_origin
            ):
                return other
            if variance == Variance.CONTRAVARIANT and not issubclass(
                field_type_origin, base_origin
            ):
                return other
        type_vars = {}
        for base_arg, field_arg in zip(get_args2(base), get_args2(field_type)):
            if base_arg in type_vars and type_vars[base_arg] != field_arg:
                return other
            type_vars[base_arg] = field_arg
    else:
        return other
    if get_origin(base) is Annotated:
        other = Annotated[(other, *get_args(base)[1:])]
    return substitute_type_vars(other, type_vars)


def resolve_field_deserialization(
    field_type: AnyType, conversion: ConvOrFunc
) -> ResolvedConversion:
    if not isinstance(conversion, Conversion):
        conversion = Conversion(conversion)
    if isinstance(conversion.converter, property):
        raise TypeError("Field deserialization cannot be a property")
    try:
        source, target = converter_types(
            conversion.converter, conversion.source, conversion.target
        )
    except TypeError:
        if conversion.target is None:
            source, target = converter_types(
                conversion.converter, conversion.source, field_type
            )
        else:
            raise
    else:
        source = handle_generic_field_type(
            field_type, target, source, Variance.COVARIANT
        )
    return ResolvedConversion.from_conversion(
        replace(conversion, source=source, target=target)
    )


def resolve_field_serialization(
    field_type: AnyType, conversion: ConvOrFunc
) -> ResolvedConversion:
    if not isinstance(conversion, Conversion):
        conversion = Conversion(conversion)
    conversion = handle_serialization_method(conversion)
    assert not isinstance(conversion.converter, property)
    try:
        source, target = converter_types(
            conversion.converter, conversion.source, conversion.target
        )
    except TypeError:
        if conversion.source is None:
            source, target = converter_types(
                conversion.converter, field_type, conversion.target
            )
        else:
            raise
    else:
        target = handle_generic_field_type(
            field_type, source, target, Variance.CONTRAVARIANT
        )
    return ResolvedConversion.from_conversion(
        replace(conversion, source=source, target=target)
    )
