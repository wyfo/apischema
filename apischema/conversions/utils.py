from inspect import Parameter, isclass, signature
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    NoReturn,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.types import AnyType
from apischema.typing import get_type_hints, is_new_type, is_type
from apischema.utils import get_origin_or_type

try:
    from apischema.typing import Annotated, Literal
except ImportError:
    Annotated, Literal = ..., ...  # type: ignore

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
            parameters = list(signature(converter.__init__).parameters.values())[1:]  # type: ignore
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


INVALID_CONVERSION_TYPES = {Union, Annotated, Literal, NoReturn}


def is_convertible(tp: AnyType) -> bool:
    origin = get_origin_or_type(tp)
    return is_new_type(tp) or (
        is_type(origin) and origin not in INVALID_CONVERSION_TYPES
    )


T = TypeVar("T")


def identity(x: T) -> T:
    return x
