from inspect import Parameter, isclass, signature
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    cast,
)

from apischema.types import AnyType, get_typed_origin
from apischema.typing import get_type_hints
from apischema.utils import type_name
from apischema.visitor import Visitor

Conversions = Mapping[AnyType, Any]
Converter = Callable[[Any], Any]
ConverterWithConversions = Tuple[Converter, Optional[Conversions]]

Param = TypeVar("Param")
Return = TypeVar("Return")


def check_converter(
    converter: Converter,
    param: Optional[Type[Param]],
    ret: Optional[Type[Return]],
    namespace: Dict[str, Any] = None,
) -> Tuple[Type[Param], Type[Return]]:
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
    return cast(Type[Param], param), cast(Type[Return], ret)


Cls = TypeVar("Cls", bound=Type)
Other = TypeVar("Other", bound=Type)


def substitute_type_vars(base: Cls, other: Other) -> Tuple[Cls, Other]:
    if getattr(base, "__origin__", None) is None:
        return base, other
    if not all(isinstance(arg, TypeVar) for arg in base.__args__):  # type: ignore
        raise TypeError(
            f"Generic conversion doesn't support partial specialization,"
            f" aka {type_name(base)}[{','.join(map(type_name, base.__args__))}]"
        )
    substitution = dict(zip(base.__args__, get_typed_origin(base).__parameters__))
    if isinstance(other, TypeVar):  # type: ignore
        new_other = substitution.get(other, other)
    elif getattr(other, "__origin__", None) is not None:
        new_other = get_typed_origin(other)[
            tuple(substitution.get(arg, arg) for arg in other.__args__)
        ]
    else:
        new_other = other
    return cast(Tuple[Cls, Other], (get_typed_origin(base), new_other))


class ConvertibleVisitor(Visitor):
    def annotated(self, cls: AnyType, annotations: Sequence[Any], _):
        raise NotImplementedError()

    def new_type(self, cls: AnyType, super_type: AnyType, _):
        raise NotImplementedError()

    def _type_var(self, tv: AnyType, _):
        raise NotImplementedError()

    def visit_not_builtin(self, cls: AnyType, _):
        return


def is_convertible(cls: AnyType):
    try:
        ConvertibleVisitor().visit(cls, ...)
    except NotImplementedError:
        return False
    else:
        return True


def check_convertible(cls: AnyType):
    if not is_convertible(cls):
        raise TypeError(f"{type_name(cls)} is not a class")
