import sys
from dataclasses import (  # type: ignore
    Field,
    InitVar,
    MISSING,
    _FIELDS,
    _FIELD_CLASSVAR,
    is_dataclass,
    make_dataclass,
)
from functools import lru_cache
from itertools import chain
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Set,
    TYPE_CHECKING,
    Tuple,
    Type,
)

from apischema.dependent_required import (
    DEPENDENT_REQUIRED_ATTR,
    DependentRequired,
    Requirements,
)
from apischema.metadata.implem import ConversionMetadata
from apischema.metadata.keys import ALIAS_METADATA, CONVERSIONS_METADATA
from apischema.types import AnyType
from apischema.typing import get_type_hints, get_type_hints2
from apischema.utils import (
    OperationKind,
    PREFIX,
    get_origin2,
    get_origin_or_type,
    has_type_vars,
)

if TYPE_CHECKING:
    from apischema.conversions.conversions import Conversions

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

if sys.version_info <= (3, 7):  # pragma: no cover
    is_dataclass_ = is_dataclass

    def is_dataclass(obj) -> bool:
        return is_dataclass_(obj) and getattr(obj, "__origin__", None) is None


@lru_cache()
def dataclass_types_and_fields(
    tp: AnyType,
) -> Tuple[Mapping[str, AnyType], Sequence[Field], Sequence[Field]]:
    from apischema.metadata.keys import INIT_VAR_METADATA

    cls = get_origin_or_type(tp)
    assert is_dataclass(cls)
    types = get_type_hints2(tp)
    fields, init_fields = [], []
    for field in getattr(cls, _FIELDS).values():
        assert isinstance(field, Field)
        if field._field_type == _FIELD_CLASSVAR:  # type: ignore
            continue
        field_type = types[field.name]
        if isinstance(field_type, InitVar):
            types[field.name] = field_type.type  # type: ignore
            init_fields.append(field)
        elif field_type is InitVar:
            metadata = getattr(cls, _FIELDS)[field.name].metadata
            if INIT_VAR_METADATA not in metadata:
                raise TypeError("Before 3.8, InitVar requires init_var metadata")
            init_field = (PREFIX, metadata[INIT_VAR_METADATA], ...)
            tmp_cls = make_dataclass("Tmp", [init_field], bases=(cls,))  # type: ignore
            types[field.name] = get_type_hints(tmp_cls, include_extras=True)[PREFIX]
            if has_type_vars(types[field.name]):
                raise TypeError("Generic InitVar are not supported before 3.8")
            init_fields.append(field)
        else:
            fields.append(field)
    # Use immutable return because of cache
    return MappingProxyType(types), tuple(fields), tuple(init_fields)


def get_fields(
    fields: Sequence[Field], init_vars: Sequence[Field], operation: OperationKind
) -> Sequence[Field]:
    from apischema.metadata.keys import SKIP_METADATA

    fields_by_operation = {
        OperationKind.DESERIALIZATION: chain((f for f in fields if f.init), init_vars),
        operation.SERIALIZATION: fields,
    }[operation]
    return [f for f in fields_by_operation if SKIP_METADATA not in f.metadata]


def has_default(field: Field) -> bool:
    return field.default is not MISSING or field.default_factory is not MISSING  # type: ignore # noqa: E501


def is_required(field: Field) -> bool:
    from apischema.metadata.keys import REQUIRED_METADATA

    return REQUIRED_METADATA in field.metadata or not has_default(field)


def get_default(field: Field) -> Any:
    if field.default_factory is not MISSING:  # type: ignore
        return field.default_factory()  # type: ignore
    if field.default is not MISSING:
        return field.default
    raise NotImplementedError


def get_alias(field: Field) -> str:
    return field.metadata.get(ALIAS_METADATA, field.name)


def get_requirements(
    cls: Type,
    method: Callable[[DependentRequired], Requirements],
    operation: OperationKind,
) -> Requirements:
    assert is_dataclass(cls)
    _, fields, init_vars = dataclass_types_and_fields(cls)  # type: ignore
    all_dependent_required: Collection["DependentRequired"] = getattr(
        cls, DEPENDENT_REQUIRED_ATTR, ()
    )
    requirements: Dict[Field, Set[Field]] = {}
    fields_by_operation = get_fields(fields, init_vars, operation)
    for dep_req in all_dependent_required:
        for field, required in method(dep_req).items():  # noqa: F402
            requirements.setdefault(field, set()).update(
                req for req in required if req in fields_by_operation
            )
    return requirements


def check_merged_class(merged_cls: AnyType) -> Type:
    origin = get_origin2(merged_cls)
    if origin is None:
        origin = merged_cls
    if not is_dataclass(origin):
        raise TypeError("Merged field must have dataclass type")
    return origin


def get_field_conversions(
    field: Field, operation: OperationKind
) -> Optional["Conversions"]:

    if CONVERSIONS_METADATA not in field.metadata:
        return None
    else:
        conversions: ConversionMetadata = field.metadata[CONVERSIONS_METADATA]
        return {
            OperationKind.DESERIALIZATION: conversions.deserialization,
            OperationKind.SERIALIZATION: conversions.serialization,
        }[operation]
