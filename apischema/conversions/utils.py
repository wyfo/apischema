from inspect import Parameter, isclass, signature
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    cast,
)

from apischema.types import AnyType, subscriptable_origin
from apischema.typing import get_args, get_origin, get_type_hints
from apischema.utils import type_name
from apischema.visitor import Visitor

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

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


TV = AnyType


def type_var_remap(
    base: AnyType, other: AnyType
) -> Iterator[Tuple[TV, TV]]:  # type: ignore
    if isinstance(base, TypeVar) and isinstance(other, TypeVar):  # type: ignore
        yield other, base
        return
    base_origin, other_origin = get_origin(base), get_origin(other)
    if (
        base_origin is None
        or other_origin is None
        or len(get_args(base)) != len(get_args(other))
        or not issubclass(other_origin, base_origin)
    ):
        return
    for base_arg, other_arg in zip(get_args(base), get_args(other)):
        yield from type_var_remap(base_arg, other_arg)


def substitute_type_vars(
    cls: AnyType, substitutions: Mapping[TV, TV]  # type: ignore
) -> AnyType:
    if isinstance(cls, TypeVar):  # type: ignore
        return substitutions.get(cls, cls)
    elif get_origin(cls) is not None:
        if get_origin(cls) is Annotated:
            annotated, *metadata = get_args(cls)
            return Annotated[  # type: ignore
                (substitute_type_vars(annotated, substitutions), *metadata)
            ]
        else:
            return subscriptable_origin(cls)[  # type: ignore
                tuple(substitute_type_vars(arg, substitutions) for arg in get_args(cls))
            ]
    else:
        return cls


def _substitute_type_vars(
    field_type: AnyType, base: AnyType, other: AnyType
) -> AnyType:
    return substitute_type_vars(other, dict(type_var_remap(field_type, base)))


def use_origin_type_vars(base: AnyType, other: AnyType) -> Tuple[AnyType, AnyType]:
    if get_origin(base) is None:
        return base, other
    if not all(isinstance(arg, TypeVar) for arg in get_args(base)):  # type: ignore
        raise TypeError(
            f"Generic conversion doesn't support specialization,"
            f" aka {type_name(base)}[{','.join(map(type_name, get_args(base)))}]"
        )
    substitution = dict(zip(get_args(base), subscriptable_origin(base).__parameters__))
    return subscriptable_origin(base), substitute_type_vars(other, substitution)


class ConvertibleVisitor(Visitor):
    def annotated(self, cls: AnyType, annotations: Sequence[Any]):
        raise NotImplementedError()

    def new_type(self, cls: AnyType, super_type: AnyType):
        raise NotImplementedError()

    def _type_var(self, tv: AnyType):
        raise NotImplementedError()

    def visit_not_builtin(self, cls: AnyType):
        return


def is_convertible(cls: AnyType):
    try:
        ConvertibleVisitor().visit(cls)
    except NotImplementedError:
        return False
    else:
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
