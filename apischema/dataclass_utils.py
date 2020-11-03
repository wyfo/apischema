import sys
from dataclasses import (  # type: ignore
    Field,
    InitVar,
    MISSING,
    _FIELDS,
    _FIELD_CLASSVAR,
    field,
    is_dataclass,
    make_dataclass,
)
from functools import partial
from typing import (
    AbstractSet,
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Set,
    Tuple,
    Type,
    cast,
)

from apischema.dependent_required import DEPENDENT_REQUIRED_ATTR, DependentRequired
from apischema.types import AnyType
from apischema.typing import get_type_hints, get_origin
from apischema.utils import PREFIX

if sys.version_info <= (3, 7):  # pragma: no cover
    is_dataclass_ = is_dataclass

    def is_dataclass(obj) -> bool:
        return is_dataclass_(obj) and getattr(obj, "__origin__", None) is None


def get_all_fields(cls: Type) -> Mapping[str, Field]:
    from apischema.metadata.keys import SKIP_METADATA

    fields: Collection[Field] = getattr(cls, _FIELDS).values()
    assert is_dataclass(cls)
    return {
        field.name: field
        for field in sorted(fields, key=lambda f: f.name)
        if field._field_type != _FIELD_CLASSVAR  # type: ignore
        and SKIP_METADATA not in field.metadata
    }


def resolve_dataclass_types(
    cls: Type,
) -> Tuple[Mapping[str, AnyType], Collection[str]]:
    from apischema.metadata.keys import INIT_VAR_METADATA

    types = get_type_hints(cls, include_extras=True)
    init_fields = []
    for name, field_type in types.items():
        if isinstance(field_type, InitVar):
            types[name] = field_type.type  # type: ignore
            init_fields.append(name)
        elif field_type is InitVar:
            metadata = getattr(cls, _FIELDS)[name].metadata
            if INIT_VAR_METADATA not in metadata:
                raise TypeError("Before 3.8, InitVar requires init_var metadata")
            init_field = (PREFIX, metadata[INIT_VAR_METADATA], field(default=...))
            tmp_cls = make_dataclass("Tmp", [init_field], bases=(cls,))  # type: ignore
            types[name] = get_type_hints(tmp_cls, include_extras=True)[PREFIX]
            init_fields.append(name)
    return types, init_fields


def has_default(field: Field) -> bool:
    return field.default is not MISSING or field.default_factory is not MISSING  # type: ignore # noqa E501


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
    from apischema import settings
    from apischema.metadata.keys import ALIAS_METADATA

    return settings.aliaser()(field.metadata.get(ALIAS_METADATA, field.name))


Requirements = Mapping[str, AbstractSet[str]]


def _merge_requirements(
    cls: Type, method: Callable[[DependentRequired], Mapping[Field, AbstractSet[Field]]]
) -> Tuple[Requirements, Requirements]:
    assert is_dataclass(cls)
    _, init_only = resolve_dataclass_types(cls)
    init_only = set(init_only)
    all_dependent_required: Collection["DependentRequired"] = getattr(
        cls, DEPENDENT_REQUIRED_ATTR, ()
    )
    deserialization_requirements: Dict[str, AbstractSet[str]] = {}
    serialization_requirements: Dict[str, AbstractSet[str]] = {}
    for dep_req in all_dependent_required:
        for field, required in method(dep_req).items():  # noqa F402
            deserialization_requirements[field.name] = {
                get_alias(req) for req in required if req.init
            }
            serialization_requirements[field.name] = {
                get_alias(req) for req in required if req not in init_only
            }
    return deserialization_requirements, serialization_requirements


get_required_by = partial(_merge_requirements, method=DependentRequired.required_by)
get_requiring = partial(_merge_requirements, method=DependentRequired.requiring)


def get_init_merged_alias(cls: Type) -> AbstractSet[str]:
    from apischema.metadata.keys import MERGED_METADATA

    cls = cast(Type, get_origin(cls)) or cls
    if not is_dataclass(cls):
        raise TypeError("Merged field must have dataclass type")
    types = get_type_hints(cls, include_extras=True)
    result: Set[str] = set()
    for field in get_all_fields(cls).values():  # noqa F402
        if not field.init:
            continue
        if MERGED_METADATA in field.metadata:
            result |= get_init_merged_alias(types[field.name])
        else:
            result.add(get_alias(field))
    return result
