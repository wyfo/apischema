from inspect import Parameter, isclass, signature
from typing import Any, Callable, Dict, Generic, Optional, Tuple, Type, TypeVar, cast

from apischema.types import AnyType, COLLECTION_TYPES, MAPPING_TYPES, PRIMITIVE_TYPES
from apischema.typing import get_args, get_origin, get_type_hints
from apischema.utils import get_parameters, is_type_var, substitute_type_vars, type_name

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Converter = Callable[[Any], Any]


def converter_types(
    converter: Converter,
    source: Optional[AnyType] = None,
    target: Optional[AnyType] = None,
    namespace: Dict[str, Any] = None,
) -> Tuple[AnyType, AnyType]:
    try:
        # in pre 3.9, Generic __new__ perturb signature of types
        if (
            isinstance(converter, type)
            and converter.__new__ is Generic.__new__ is not object.__new__
            and converter.__init__ is not object.__init__  # type: ignore
        ):
            parameters = list(signature(converter.__init__).parameters.values())[1:]  # type: ignore # noqa: E501
        else:
            parameters = list(signature(converter).parameters.values())
    except ValueError:  # builtin types
        if target is None and isclass(converter):
            target = cast(Type[Any], converter)
        if source is None:
            raise TypeError("Converter source is unknown") from None
    else:
        if not parameters:
            raise TypeError("converter must have at least one parameter")
        first_param, *other_params = parameters
        for p in other_params:
            if p.default is Parameter.empty and p.kind not in (
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
            ):
                raise TypeError(
                    "converter must have at most one parameter without default"
                )
        if source is not None and target is not None:
            return source, target
        types = get_type_hints(converter, None, namespace, include_extras=True)
        if not types and isclass(converter):
            types = get_type_hints(
                converter.__new__, None, namespace, include_extras=True
            ) or get_type_hints(
                converter.__init__, None, namespace, include_extras=True  # type: ignore
            )
        if source is None:
            try:
                source = types.pop(first_param.name)
            except KeyError:
                raise TypeError("converter source is unknown") from None
        if target is None:
            try:
                target = types.pop("return")
            except KeyError:
                if isclass(converter):
                    target = cast(Type, converter)
                else:
                    raise TypeError("converter target is unknown") from None
    return source, target


def get_conversion_type(base: AnyType, other: AnyType) -> Tuple[AnyType, AnyType]:
    """
    Args:
        base: (generic) type on the registered side the conversion
        other: other side of the conversion

    Returns:
        The type on which is registered conversion (its origin when generic) and the
        other side of the conversion with its original parameters
    """
    origin = get_origin(base)
    if origin is Annotated:
        raise TypeError("Annotated types cannot have conversions")
    if origin is None:
        return base, other
    args = get_args(base)
    if not all(map(is_type_var, args)):
        raise TypeError(
            f"Generic conversion doesn't support specialization,"
            f" aka {type_name(base)}[{','.join(map(type_name, args))}]"
        )
    return origin, substitute_type_vars(other, dict(zip(args, get_parameters(origin))))


BUILTIN_TYPES = {*PRIMITIVE_TYPES, *COLLECTION_TYPES, *MAPPING_TYPES}


def is_convertible(tp: AnyType) -> bool:
    return isinstance(tp, type) and tp not in BUILTIN_TYPES


T = TypeVar("T")


def identity(x: T) -> T:
    return x
