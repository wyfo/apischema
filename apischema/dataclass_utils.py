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
from functools import lru_cache, partial
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Collection,
    Mapping,
    Sequence,
    Tuple,
    Type,
)

from apischema.dependent_required import (
    DEPENDENT_REQUIRED_ATTR,
    DependentRequired,
    Requirements,
)
from apischema.types import AnyType
from apischema.typing import get_origin, get_type_hints
from apischema.utils import PREFIX

if sys.version_info <= (3, 7):  # pragma: no cover
    is_dataclass_ = is_dataclass

    def is_dataclass(obj) -> bool:
        return is_dataclass_(obj) and getattr(obj, "__origin__", None) is None


@lru_cache()
def dataclass_types_and_fields(
    cls: Type,
) -> Tuple[Mapping[str, AnyType], Sequence[Field], Sequence[Field]]:
    from apischema.metadata.keys import INIT_VAR_METADATA

    assert is_dataclass(cls)
    types = get_type_hints(cls, include_extras=True)
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
            init_fields.append(field)
        else:
            fields.append(field)
    # Use immutable return because of cache
    return MappingProxyType(types), tuple(fields), tuple(init_fields)


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
    raise NotImplementedError()


def get_alias(field: Field) -> str:
    from apischema.metadata.keys import ALIAS_METADATA

    return field.metadata.get(ALIAS_METADATA, field.name)


def _merge_requirements(
    cls: Type,
    method: Callable[[DependentRequired], Requirements],
) -> Tuple[Requirements, Requirements]:
    assert is_dataclass(cls)
    _, _, init_vars = dataclass_types_and_fields(cls)  # type: ignore
    init_only = {f.name for f in init_vars}
    all_dependent_required: Collection["DependentRequired"] = getattr(
        cls, DEPENDENT_REQUIRED_ATTR, ()
    )
    deserialization_requirements = {}
    serialization_requirements = {}
    for dep_req in all_dependent_required:
        for field, required in method(dep_req).items():  # noqa: F402
            deserialization_requirements[field] = {req for req in required if req.init}
            serialization_requirements[field] = {
                req for req in required if req not in init_only
            }
    return deserialization_requirements, serialization_requirements


get_required_by = partial(_merge_requirements, method=DependentRequired.required_by)
get_requiring = partial(_merge_requirements, method=DependentRequired.requiring)


def check_merged_class(merged_cls: AnyType) -> Type:
    origin = get_origin(merged_cls)
    if origin is None:
        origin = merged_cls
    if not is_dataclass(origin):
        raise TypeError("Merged field must have dataclass type")
    return origin
