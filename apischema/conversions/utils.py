from inspect import Parameter, isclass, signature
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    cast,
)

from apischema.type_vars import get_parameters, resolve_type_vars
from apischema.types import AnyType
from apischema.typing import get_args, get_origin, get_type_hints
from apischema.utils import is_type_var, type_name
from apischema.visitor import Unsupported, Visitor

Conversions = Mapping[AnyType, Any]
Converter = Callable[[Any], Any]
ConverterWithConversions = Tuple[Converter, Optional[Conversions]]


def check_converter(
    converter: Converter,
    param: Optional[AnyType],
    ret: Optional[AnyType],
    namespace: Dict[str, Any] = None,
) -> Tuple[AnyType, AnyType]:
    try:
        parameters = iter(signature(converter).parameters.values())
    except ValueError:  # builtin types
        if ret is None and isclass(converter):
            ret = cast(Type[Any], converter)
        if param is None:
            raise TypeError("converter parameter must be typed")
    else:
        try:
            first = next(parameters)
        except StopIteration:
            raise TypeError("converter must have at least one parameter")
        types = get_type_hints(converter, None, namespace, include_extras=True)
        for p in parameters:
            if p.default is Parameter.empty and p.kind not in (
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
            ):
                raise TypeError(
                    "converter must have at most one parameter " "without default"
                )
        if param is None:
            try:
                param = types.pop(first.name)
            except KeyError:
                raise TypeError("converter parameter must be typed")
        if ret is None:
            try:
                ret = types.pop("return")
            except KeyError:
                if isclass(converter):
                    ret = cast(Type, converter)
                else:
                    raise TypeError("converter return must be typed")
    return param, ret


def handle_generic_conversions(
    base: AnyType, other: AnyType
) -> Tuple[AnyType, AnyType]:
    origin = get_origin(base)
    if origin is None:
        return base, other
    args = get_args(base)
    if not all(map(is_type_var, args)):
        raise TypeError(
            f"Generic conversion doesn't support specialization,"
            f" aka {type_name(base)}[{','.join(map(type_name, args))}]"
        )
    return origin, resolve_type_vars(other, dict(zip(args, get_parameters(origin))))


class ConvertibleVisitor(Visitor[bool]):
    def annotated(self, cls: AnyType, annotations: Sequence[Any]) -> bool:
        return False

    def any(self) -> bool:
        return False

    def collection(self, cls: Type[Collection], value_type: AnyType) -> bool:
        return False

    def generic(self, cls: AnyType) -> bool:
        return True

    def literal(self, values: Sequence[Any]) -> bool:
        return False

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> bool:
        return False

    def new_type(self, cls: AnyType, super_type: AnyType) -> bool:
        return False

    def tuple(self, types: Sequence[AnyType]) -> bool:
        return False

    def union(self, alternatives: Sequence[AnyType]) -> bool:
        return False


def is_convertible(cls: AnyType):
    try:
        return ConvertibleVisitor().visit(cls)
    except (NotImplementedError, Unsupported):
        return True


def check_convertible(cls: AnyType):
    if not is_convertible(cls):
        raise TypeError(f"{type_name(cls)} is not a class")


class ConversionsWrapper:
    """Allows to hash conversions — conversions must be immutable"""

    def __init__(self, conversions: Conversions):
        self.conversions = conversions

    def __hash__(self):
        return id(self.conversions)


identity = lambda x: x  # noqa: E731
