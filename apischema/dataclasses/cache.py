import dataclasses
from enum import Enum, auto
from inspect import getmembers
from typing import (  # type: ignore
    AbstractSet,
    Any,
    Callable,
    Collection,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Set,
    TYPE_CHECKING,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from apischema.conversion.conversions import ConversionsMetadata
from apischema.conversion.utils import (
    Conversions,
    check_converter,
    substitute_type_vars,
)
from apischema.conversion.visitor import (
    ConversionsVisitor,
    Deserialization,
    Serialization,
)
from apischema.dependencies import DependentRequired
from apischema.metadata.keys import (
    ALIAS_METADATA,
    CONVERSIONS_METADATA,
    DEFAULT_FALLBACK_METADATA,
    INCOMPATIBLE_WITH_MERGED,
    INCOMPATIBLE_WITH_PROPERTIES,
    INIT_VAR_METADATA,
    MERGED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SCHEMA_METADATA,
    SKIP_METADATA,
    VALIDATORS_METADATA,
)
from apischema.types import AnyType
from apischema.typing import get_type_hints
from apischema.utils import PREFIX
from apischema.validation.validator import VALIDATORS_ATTR, Validator, validate
from apischema.visitor import visitor_method

if TYPE_CHECKING:
    from apischema.json_schema.annotations import Annotations
    from apischema.json_schema.constraints import Constraints

Cls = TypeVar("Cls", bound=Type)


def slotted_dataclass(cls: Cls) -> Cls:
    slots = [f.name for f in dataclasses.fields(cls)]
    namespace = cls.__dict__.copy()
    for slot in slots:
        namespace.pop(slot, ...)
    namespace["__slots__"] = slots
    return cast(Cls, type(cls.__name__, cls.__bases__, namespace))


class FieldKind(Enum):
    INIT = auto()
    NORMAL = auto()
    NO_INIT = auto()

    def __and__(self, other: "FieldKind"):
        return (self != FieldKind.INIT and other != FieldKind.INIT) or (
            self != FieldKind.NO_INIT and other != FieldKind.NO_INIT
        )


@slotted_dataclass
@dataclasses.dataclass
class Field:
    alias: str
    annotations: Optional["Annotations"]
    base_field: dataclasses.Field
    constraints: Optional["Constraints"]
    default_fallback: bool
    default: bool
    deserialization_conversions: Optional[Conversions]
    deserialization_method: Callable
    deserialization_type: AnyType
    kind: FieldKind
    name: str
    post_init: bool
    serialization_conversions: Optional[Conversions]
    serialization_method: Callable
    serialization_type: AnyType
    type: AnyType
    validators: Optional[Sequence[Validator]]

    deserialization_required_by: AbstractSet[str] = frozenset()
    serialization_required_by: AbstractSet[str] = frozenset()


FieldCache = Tuple[
    Sequence[Field],
    Sequence[Tuple[AbstractSet[str], Field]],
    Sequence[Tuple[Union[Pattern, "ellipsis"], Field]],  # noqa F821
    Optional[Field],
]
_deserialization_fields: Dict[Type, FieldCache] = {}
AggregateFieldCache = Tuple[Sequence[Field], Sequence[Field]]
_aggregate_serialization_fields: Dict[Type, AggregateFieldCache] = {}
# Because dataclasses with InitVar doesn't have to have a __post_init__
# (they could only be used in validators), theses classes has to be flagged
_post_init_classes: Set[Type] = set()


def _to_aggregate(cache: FieldCache) -> AggregateFieldCache:
    fields, merged, pattern, additional = cache
    additional_ = [additional] if additional is not None else []
    return fields, [f for _, f in merged] + [f for _, f in pattern] + additional_


def _from_aggregate(aggregate_cache: AggregateFieldCache) -> FieldCache:
    fields, aggregate_fields = aggregate_cache
    merged_fields: List[Tuple[AbstractSet[str], Field]] = []
    pattern_fields: List[Tuple[Pattern, Field]] = []
    additional_fields = None
    for field in aggregate_fields:
        metadata = field.base_field.metadata
        if MERGED_METADATA in metadata:
            merged_fields.append((frozenset(_merged_aliases(field.type)), field))
        else:
            pattern = metadata[PROPERTIES_METADATA]
            if pattern is not None:
                pattern_fields.append((pattern, field))
            else:
                additional_fields = field
    return fields, merged_fields, pattern_fields, additional_fields


T = TypeVar("T")


def _add_field_to_lists(
    obj: T, kind: FieldKind, deserializations: List[T], serializations: List[T]
):
    if kind != FieldKind.INIT:
        serializations.append(obj)
    if kind != FieldKind.NO_INIT:
        deserializations.append(obj)


def _resolve_init_var(cls: AnyType, field: dataclasses.Field) -> AnyType:
    if INIT_VAR_METADATA not in field.metadata:
        raise TypeError("Before 3.8, InitVar requires init_var metadata")

    tmp_cls = dataclasses.make_dataclass(
        "Tmp",
        [
            (
                PREFIX,
                field.metadata[INIT_VAR_METADATA],
                dataclasses.field(default=cast(Any, None)),
            )
        ],
        bases=(cls,),
    )
    return get_type_hints(tmp_cls, include_extras=True)[PREFIX]


def _handle_method_conversions(
    method: Callable, conversions: Optional[Conversions]
) -> Callable:
    if conversions is None:
        return method

    def wrapper(self: ConversionsVisitor, *arg):
        conversions_save = self.conversions
        self.conversions = conversions
        try:
            return method(self, *arg)
        finally:
            self.conversions = conversions_save

    return wrapper


def _deserialization_method(
    deserialization_type: Type,
    deserialization: Optional[Deserialization],
    conversions: Optional[Conversions],
) -> Callable:
    from apischema.deserialization.deserializer import (
        Deserializer,
        DataWithConstraint,
    )

    if deserialization is None:
        return _handle_method_conversions(
            visitor_method(deserialization_type, Deserializer), conversions
        )
    else:

        def deserialization_method(  # type: ignore
            visitor: Deserializer, cls: AnyType, data2: DataWithConstraint
        ):  # type: ignore
            assert deserialization is not None
            return visitor.visit_conversion(cls, deserialization, data2)

        return deserialization_method


def _deserialization(
    field_type: AnyType, metadata: Mapping[str, Any],
) -> Tuple[
    AnyType,
    Optional[Deserialization],
    Optional[Conversions],
    Callable,
    Optional[Sequence[Validator]],
]:
    validators: Optional[Sequence[Validator]] = None
    if VALIDATORS_METADATA in metadata:
        validators = metadata[VALIDATORS_METADATA].validators
    conversions = metadata.get(CONVERSIONS_METADATA, ConversionsMetadata())
    deserialization_conversions: Optional[Conversions]
    deserialization: Optional[Deserialization]
    if conversions.both is not None:
        deserialization_conversions = {field_type: conversions.both}
    elif conversions.deserialization is not None:
        deserialization_conversions = conversions.deserialization
    else:
        deserialization_conversions = None
    # Embed validators in conversion in order to have only one if in deserialization
    # `if field.deserializer is not None`
    if conversions.deserializer is not None:
        converter = conversions.deserializer
        param, ret = check_converter(converter, None, field_type)  # type: ignore
        ret, param = substitute_type_vars(ret, param)  # type: ignore
        if validators:
            converter = lambda data, conv=converter: validate(  # noqa E731
                conv(data), validators
            )
        deserialization_type = param
        deserialization = {param: (converter, deserialization_conversions)}
    elif validators:
        deserialization_type = field_type
        deserialization = {
            field_type: ((lambda data: validate(data, validators)), None)
        }
    else:
        deserialization_type = field_type
        deserialization = None
    return (
        deserialization_type,
        deserialization,
        deserialization_conversions,
        _deserialization_method(
            field_type, deserialization, deserialization_conversions
        ),
        validators,
    )


def _serialization_method(
    serialization_type: Type,
    serialization: Optional[Serialization],
    conversions: Optional[Conversions],
) -> Callable:
    from apischema.serialization import (
        Serializer,
        PRIMITIVE_TYPES_SET,
        COLLECTION_TYPE_SET,
    )

    if serialization is None:
        # TODO could be optimized
        if serialization_type in PRIMITIVE_TYPES_SET:

            def serialization_method(visitor: Serializer, obj):
                return obj

        elif serialization_type in COLLECTION_TYPE_SET:

            def serialization_method(visitor: Serializer, obj):
                return [visitor.visit2(elt) for elt in obj]

        elif serialization_type is dict:

            def serialization_method(visitor: Serializer, obj):
                return {
                    visitor.visit2(key): visitor.visit2(value)
                    for key, value in obj.items()
                }

        else:
            serialization_method = Serializer.visit2
        return _handle_method_conversions(serialization_method, conversions)
    else:

        def serialization_method(visitor: Serializer, obj):  # type: ignore
            assert serialization is not None
            return visitor.visit_conversion(..., serialization, obj)

        return serialization_method


def _serialization(
    field_type: AnyType, metadata: Mapping[str, Any]
) -> Tuple[AnyType, Optional[Serialization], Optional[Conversions], Callable]:
    conversions = metadata.get(CONVERSIONS_METADATA, ConversionsMetadata())
    serialization_conversions: Optional[Conversions]
    serialization: Optional[Serialization]
    if conversions.both is not None:
        serialization_conversions = {field_type: conversions.both}
    elif conversions.deserialization is not None:
        serialization_conversions = conversions.deserialization
    else:
        serialization_conversions = None
    if conversions.serializer is not None:
        converter = conversions.serializer
        param, ret = check_converter(converter, field_type, None)  # type: ignore
        param, ret = substitute_type_vars(param, ret)  # type: ignore
        serialization_type = ret
        serialization = ret, (converter, serialization_conversions)
    else:
        serialization_type = field_type
        serialization = None
    return (
        serialization_type,
        serialization,
        serialization_conversions,
        _serialization_method(
            serialization_type, serialization, serialization_conversions
        ),
    )


def _merged_aliases(cls: Type) -> Iterable[str]:
    assert dataclasses.is_dataclass(cls)
    types = get_type_hints(cls, include_extras=True)
    for field in dataclasses.fields(cls):
        if MERGED_METADATA in field.metadata:
            # No need to check overlapping here because it will be checked
            # when merged dataclass will be cached
            yield from _merged_aliases(types[field.name])
        elif PROPERTIES_METADATA in field.metadata:
            raise TypeError("Merged dataclass cannot have properties field")
        else:
            yield field.metadata.get(ALIAS_METADATA, field.name)


def _check_fields_overlap(present: Set[str], other: AbstractSet[str]):
    if present & other:
        raise TypeError(f"Merged fields {present & other} overlap")
    present.update(other)


def _update_dependencies(cls: AnyType, all_fields: Mapping[str, Field]):
    for validator in getattr(cls, VALIDATORS_ATTR, ()):
        validator.dependencies = {
            dep for dep in validator.dependencies if dep in all_fields
        }
    all_dependencies: Collection[DependentRequired] = [
        m for _, m in getmembers(cls, lambda m: isinstance(m, DependentRequired))
    ]
    for dependencies in all_dependencies:
        for base_field, required in dependencies.required_by().items():
            field = all_fields[base_field.name]
            field.deserialization_required_by = {
                all_fields[req.name].alias
                for req in required
                if all_fields[req.name].kind != FieldKind.NO_INIT
            }
            field.serialization_required_by = {
                all_fields[req.name].alias
                for req in required
                if all_fields[req.name].kind != FieldKind.INIT
            }


F = TypeVar("F", bound=Union[Field, Tuple[Any, Field]])


def _filter_by_kind(field_list: Iterable[F], kind: FieldKind) -> Sequence[F]:
    fields = [(elt, elt[1] if isinstance(elt, tuple) else elt) for elt in field_list]
    return [elt for elt, field in fields if field.kind != kind]


@dataclasses.dataclass
class FieldLists:
    cls: Type
    normal: List[Field] = dataclasses.field(default_factory=list)
    merged: List[Tuple[AbstractSet, Field]] = dataclasses.field(default_factory=list)
    pattern: List[Tuple[Pattern, Field]] = dataclasses.field(default_factory=list)
    additional: List[Field] = dataclasses.field(default_factory=list)

    def remove_kind(self, remove: FieldKind) -> FieldCache:
        additional = _filter_by_kind(self.additional, remove)
        if len(additional) > 1:
            raise TypeError(
                f"{self.cls.__name__} cannot have more than one properties field"
            )
        return (
            _filter_by_kind(self.normal, remove),
            _filter_by_kind(self.merged, remove),
            _filter_by_kind(self.pattern, remove),
            additional[0] if additional else None,
        )


def cache_fields(cls: Type):
    assert dataclasses.is_dataclass(cls)
    types = get_type_hints(cls, include_extras=True)
    lists = FieldLists(cls)
    all_fields: Dict[str, Field] = {}
    all_merged_aliases: Set[str] = set()
    for field in getattr(cls, dataclasses._FIELDS).values():  # type: ignore
        if field._field_type == dataclasses._FIELD_CLASSVAR:  # type: ignore
            continue
        metadata = field.metadata
        if SKIP_METADATA in metadata:
            continue
        error_prefix = f"{cls.__name__}.{field.name}: "
        type_ = types[field.name]
        if isinstance(type_, dataclasses.InitVar):
            kind = FieldKind.INIT
            type_ = type_.type  # type: ignore
        elif type_ is dataclasses.InitVar:
            kind = FieldKind.INIT
            type_ = _resolve_init_var(cls, field)
        elif field.init:
            kind = FieldKind.NORMAL
        else:
            kind = FieldKind.NO_INIT
        if kind == FieldKind.INIT:
            _post_init_classes.add(cls)
        default = REQUIRED_METADATA not in metadata and (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING  # type: ignore
        )
        (
            deserialization_type,
            deserialization,
            deserialization_conversions,
            deserialization_method,
            validators,
        ) = _deserialization(type_, metadata)
        (
            serialization_type,
            serialization,
            serialization_conversions,
            serialization_method,
        ) = _serialization(type_, metadata)

        from apischema import settings
        from apischema.json_schema.schema import Schema

        schema = metadata.get(SCHEMA_METADATA, Schema())

        new_field = Field(
            alias=settings.aliaser()(metadata.get(ALIAS_METADATA, field.name)),
            annotations=schema.annotations,
            base_field=field,
            constraints=schema.constraints,
            default=default,
            default_fallback=metadata.get(DEFAULT_FALLBACK_METADATA, False),
            deserialization_conversions=deserialization_conversions,
            deserialization_method=deserialization_method,
            deserialization_type=deserialization_type,
            kind=kind,
            name=field.name,
            post_init=metadata.get(POST_INIT_METADATA, False),
            serialization_conversions=serialization_conversions,
            serialization_method=serialization_method,
            serialization_type=serialization_type,
            type=field.type,
            validators=validators,
        )
        all_fields[field.name] = new_field
        if MERGED_METADATA in metadata:
            if any(key in metadata for key in INCOMPATIBLE_WITH_MERGED):
                raise TypeError(f"{error_prefix}Incompatible metadata with merged")
            if not dataclasses.is_dataclass(type_):
                raise TypeError(
                    f"{error_prefix}Merged field must have a dataclass type"
                )
            merged_aliases: AbstractSet[str] = frozenset(_merged_aliases(type_))
            _check_fields_overlap(all_merged_aliases, merged_aliases)
            lists.merged.append((merged_aliases, new_field))
        elif PROPERTIES_METADATA in metadata:
            if any(key in metadata for key in INCOMPATIBLE_WITH_PROPERTIES):
                raise TypeError(f"{error_prefix}Incompatible metadata with properties")
            pattern = metadata[PROPERTIES_METADATA]
            if pattern is None:
                lists.additional.append(new_field)
            else:
                lists.pattern.append((pattern, new_field))
        else:
            lists.normal.append(new_field)
    _check_fields_overlap(all_merged_aliases, all_fields.keys())
    _update_dependencies(cls, all_fields)
    _deserialization_fields[cls] = lists.remove_kind(FieldKind.NO_INIT)
    _aggregate_serialization_fields[cls] = _to_aggregate(
        lists.remove_kind(FieldKind.INIT)
    )


def get_deserialization_fields(cls: Type) -> FieldCache:
    try:
        return _deserialization_fields[cls]
    except KeyError:
        cache_fields(cls)
        # Use recursion because of potential concurrent reset_dataclasses_cache
        return get_deserialization_fields(cls)


def get_serialization_fields(cls: Type) -> FieldCache:
    return _from_aggregate(get_aggregate_serialization_fields(cls))


def get_aggregate_serialization_fields(cls: Type) -> AggregateFieldCache:
    try:
        return _aggregate_serialization_fields[cls]
    except KeyError:
        cache_fields(cls)
        return get_aggregate_serialization_fields(cls)


def has_post_init_fields(cls: Type) -> bool:
    if cls not in _deserialization_fields:
        cache_fields(cls)
    return cls in _post_init_classes


def reset_dataclasses_cache():
    _deserialization_fields.clear()
    _aggregate_serialization_fields.clear()
