import inspect
from typing import (
    Any,
    Callable,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.cache import cache
from apischema.metadata import properties
from apischema.objects.fields import ObjectField
from apischema.objects.visitor import ObjectVisitor
from apischema.types import AnyType, OrderedDict
from apischema.typing import _GenericAlias, get_type_hints
from apischema.utils import empty_dict
from apischema.visitor import Unsupported


@cache
def object_fields(
    tp: AnyType,
    deserialization: bool = False,
    serialization: bool = False,
    default: Optional[
        Callable[[type], Optional[Sequence[ObjectField]]]
    ] = ObjectVisitor._default_fields,
) -> Mapping[str, ObjectField]:
    class GetFields(ObjectVisitor[Sequence[ObjectField]]):
        def _skip_field(self, field: ObjectField) -> bool:
            return (field.skip.deserialization and serialization) or (
                field.skip.serialization and deserialization
            )

        @staticmethod
        def _default_fields(cls: type) -> Optional[Sequence[ObjectField]]:
            return None if default is None else default(cls)

        def object(
            self, cls: Type, fields: Sequence[ObjectField]
        ) -> Sequence[ObjectField]:
            return fields

    try:
        return OrderedDict((f.name, f) for f in GetFields().visit(tp))
    except (Unsupported, NotImplementedError):
        raise TypeError(f"{tp} doesn't have fields")


def object_fields2(obj: Any) -> Mapping[str, ObjectField]:
    return object_fields(
        obj if isinstance(obj, (type, _GenericAlias)) else obj.__class__
    )


T = TypeVar("T")


class FieldGetter:
    def __init__(self, obj: Any):
        self.fields = object_fields2(obj)

    def __getattribute__(self, name: str) -> ObjectField:
        try:
            return object.__getattribute__(self, "fields")[name]
        except KeyError:
            raise AttributeError(name)


@overload
def get_field(obj: Type[T]) -> T:
    ...


@overload
def get_field(obj: T) -> T:
    ...


# Overload because of Mypy issue
# https://github.com/python/mypy/issues/9003#issuecomment-667418520
def get_field(obj: Union[Type[T], T]) -> T:
    return cast(T, FieldGetter(obj))


class AliasedStr(str):
    pass


class AliasGetter:
    def __init__(self, obj: Any):
        self.fields = object_fields2(obj)

    def __getattribute__(self, name: str) -> str:
        try:
            return AliasedStr(object.__getattribute__(self, "fields")[name].alias)
        except KeyError:
            raise AttributeError(name)


@overload
def get_alias(obj: Type[T]) -> T:
    ...


@overload
def get_alias(obj: T) -> T:
    ...


def get_alias(obj: Union[Type[T], T]) -> T:
    return cast(T, AliasGetter(obj))


def parameters_as_fields(
    func: Callable, parameters_metadata: Mapping[str, Mapping] = None
) -> Sequence[ObjectField]:
    parameters_metadata = parameters_metadata or {}
    types = get_type_hints(func, include_extras=True)
    fields = []
    for param_name, param in inspect.signature(func).parameters.items():
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise TypeError("Positional only parameters are not supported")
        param_type = types.get(param_name, Any)
        if param.kind in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }:
            field = ObjectField(
                param_name,
                param_type,
                param.default is inspect.Parameter.empty,
                parameters_metadata.get(param_name, empty_dict),
                default=param.default,
            )
            fields.append(field)
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            field = ObjectField(
                param_name,
                Mapping[str, param_type],  # type: ignore
                False,
                properties | parameters_metadata.get(param_name, empty_dict),
                default_factory=dict,
            )
            fields.append(field)
    return fields
