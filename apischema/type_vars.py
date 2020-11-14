from typing import Any, Iterable, Mapping, Optional, TypeVar, Union

from apischema.types import AnyType
from apischema.typing import get_args, get_origin
from apischema.utils import is_type_var

TV = AnyType  # TypeVar is not supported as a type

# 10 should be enough for all builtin types
# but it should be an infinite list with locked appending
_type_vars = [TypeVar(f"T{i}") for i in range(10)]


def get_parameters(cls: AnyType) -> Iterable[TV]:
    return getattr(cls, "__parameters__", _type_vars)


TypeVarContext = Optional[Mapping[TV, AnyType]]


def resolve_type_vars(cls: AnyType, type_vars: TypeVarContext = None) -> Any:
    if is_type_var(cls):
        if type_vars is not None and cls in type_vars:
            return type_vars[cls]
        elif cls.__constraints__:
            return Union[cls.__constraints__]
        else:
            return Any
    elif getattr(cls, "__parameters__", ()):
        return cls[tuple(resolve_type_vars(p, type_vars) for p in cls.__parameters__)]
    else:
        return cls


def type_var_context(cls: AnyType, type_vars: TypeVarContext = None) -> TypeVarContext:
    cls = resolve_type_vars(cls, type_vars)
    origin = get_origin(cls)
    assert origin is not None
    return dict(zip(get_parameters(origin), get_args(cls)))
