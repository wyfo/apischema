__all__ = ["get_alias", "get_field", "object_fields"]
import sys
from dataclasses import Field, InitVar, MISSING, dataclass, field, replace
from types import new_class
from typing import (
    Any,
    Callable,
    ClassVar,
    Collection,
    Generic,
    Iterable,
    Mapping,
    NoReturn,
    Optional,
    Pattern,
    Sequence,
    TYPE_CHECKING,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.aliases import AliasedStr, Aliaser, get_class_aliaser
from apischema.cache import cache
from apischema.conversions.conversions import Conversion, Conversions
from apischema.conversions.utils import identity
from apischema.json_schema.constraints import Constraints
from apischema.json_schema.schemas import Schema
from apischema.metadata.implem import ConversionMetadata, ValidatorsMetadata
from apischema.metadata.keys import (
    ALIAS_METADATA,
    ALIAS_NO_OVERRIDE_METADATA,
    CONVERSION_METADATA,
    DEFAULT_AS_SET_METADATA,
    DEFAULT_FALLBACK_METADATA,
    MERGED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SCHEMA_METADATA,
    VALIDATORS_METADATA,
)
from apischema.types import AnyType, ChainMap, OrderedDict
from apischema.typing import _GenericAlias, get_args, get_origin
from apischema.utils import (
    Undefined,
    get_parameters,
    has_type_vars,
    sort_by_annotations_position,
    substitute_type_vars,
)
from apischema.visitor import Return, Unsupported, Visitor

if TYPE_CHECKING:
    from apischema.validation.validators import Validator

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

empty_dict: Mapping[str, Any] = {}

# Cannot reuse MISSING for dataclass field because it would be interpreted as no default
MISSING_DEFAULT = object()


@dataclass(frozen=True)
class ObjectField:
    name: str
    type: AnyType
    required: bool
    metadata: Mapping[str, Any] = field(default_factory=lambda: empty_dict)
    default: InitVar[Any] = MISSING_DEFAULT
    default_factory: Optional[Callable[[], Any]] = None
    aliased: bool = True

    def __post_init__(self, default: Any):
        # TODO add metadata check
        if self.default_factory is MISSING:
            object.__setattr__(self, "default_factory", None)
        if not self.required and self.default_factory is None:
            if default is MISSING_DEFAULT:
                raise ValueError("Missing default for required ObjectField")
            object.__setattr__(self, "default_factory", lambda: default)

    @property
    def additional_properties(self) -> bool:
        return self.metadata.get(PROPERTIES_METADATA, ...) is None

    @property
    def alias(self) -> str:
        str_class = AliasedStr if self.aliased else str
        return str_class(self.metadata.get(ALIAS_METADATA, self.name))

    @property
    def override_alias(self) -> bool:
        return ALIAS_NO_OVERRIDE_METADATA not in self.metadata

    @property
    def _conversion(self) -> Optional[ConversionMetadata]:
        return self.metadata.get(CONVERSION_METADATA, None)

    @property
    def default_as_set(self) -> bool:
        return DEFAULT_AS_SET_METADATA in self.metadata

    @property
    def default_fallback(self) -> bool:
        return DEFAULT_FALLBACK_METADATA in self.metadata

    @property
    def deserialization(self) -> Optional[Conversions]:
        conversion = self._conversion
        return conversion.deserialization if conversion is not None else None

    @property
    def merged(self) -> bool:
        return MERGED_METADATA in self.metadata

    @property
    def post_init(self) -> bool:
        return POST_INIT_METADATA in self.metadata

    @property
    def pattern_properties(self) -> Union[Pattern, "ellipsis", None]:  # noqa: F821
        return self.metadata.get(PROPERTIES_METADATA, None)

    @property
    def schema(self) -> Optional[Schema]:
        return self.metadata.get(SCHEMA_METADATA, None)

    @property
    def constraints(self) -> Optional[Constraints]:
        return self.schema.constraints if self.schema is not None else None

    @property
    def validators(self) -> Sequence["Validator"]:
        if VALIDATORS_METADATA in self.metadata:
            return cast(
                ValidatorsMetadata, self.metadata[VALIDATORS_METADATA]
            ).validators
        else:
            return ()

    @property
    def serialization(self) -> Optional[Conversions]:
        conversion = self._conversion
        return conversion.serialization if conversion is not None else None

    @property
    def is_aggregate(self) -> bool:
        return (
            self.merged
            or self.additional_properties
            or self.pattern_properties is not None
        )

    def get_default(self) -> Any:
        if self.required:
            raise RuntimeError("Field is required")
        assert self.default_factory is not None
        return self.default_factory()  # type: ignore


# These metadata are retrieved are not specific to fields
ANNOTATED_METADATA = {
    SCHEMA_METADATA: None,
    VALIDATORS_METADATA: ValidatorsMetadata(()),
}


def annotated_metadata(tp: AnyType) -> Mapping:
    if get_origin(tp) == Annotated:
        return ChainMap(
            ANNOTATED_METADATA,
            *(arg for arg in reversed(get_args(tp)[1:]) if isinstance(arg, Mapping)),
        )
    else:
        return empty_dict


def object_field_from_field(field: Field, field_type: AnyType) -> ObjectField:
    metadata = {**annotated_metadata(field_type), **field.metadata}
    required = REQUIRED_METADATA in metadata or (
        field.default is MISSING and field.default_factory is MISSING  # type: ignore
    )
    return ObjectField(
        field.name,
        field_type,
        required,
        metadata,
        default=field.default,
        default_factory=field.default_factory,  # type: ignore
    )


T = TypeVar("T")


if sys.version_info < (3, 7) and not TYPE_CHECKING:
    from typing import GenericMeta

    class _ObjectWrapperBaseMeta(GenericMeta):
        def __init__(cls: "ObjectWrapper", *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not hasattr(cls, "type") or cls.__origin__ is not None:
                return
            tp = cls.type[cls.__parameters__] if has_type_vars(cls.type) else cls.type
            cls.deserialization = Conversion(identity, source=cls[tp], target=tp)
            cls.serialization = Conversion(identity, source=tp, target=cls[tp])

    _ObjectWrapperBase = [_ObjectWrapperBaseMeta("ObjectWrapperBase", (), {})]
else:
    _ObjectWrapperBase = ()


@dataclass
class ObjectWrapper(*_ObjectWrapperBase, Generic[T]):  # type: ignore
    type: ClassVar[Type[T]]
    fields: ClassVar[Sequence[ObjectField]]
    wrapped: T

    deserialization: Conversion
    serialization: Conversion
    if sys.version_info >= (3, 7):

        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            tp = cls.type[cls.__parameters__] if has_type_vars(cls.type) else cls.type
            cls.deserialization = Conversion(identity, source=cls[tp], target=tp)
            cls.serialization = Conversion(identity, source=tp, target=cls[tp])


def object_wrapper(
    cls: Type[T], fields: Iterable[ObjectField]
) -> Type[ObjectWrapper[T]]:
    return new_class(
        f"{cls.__name__}{ObjectWrapper.__name__}",
        (ObjectWrapper[T],),
        exec_body=lambda ns: ns.update({"type": cls, "fields": list(fields)}),
    )


def override_alias(field: ObjectField, aliaser: Aliaser) -> ObjectField:
    if field.override_alias:
        return replace(
            field,
            metadata={**field.metadata, ALIAS_METADATA: aliaser(field.alias)},
            default=MISSING_DEFAULT,
        )
    else:
        return field


def apply_class_aliaser(
    cls: Type, fields: Sequence[ObjectField]
) -> Sequence[ObjectField]:
    aliaser = get_class_aliaser(cls)
    return fields if aliaser is None else [override_alias(f, aliaser) for f in fields]


class ObjectVisitor(Visitor[Return]):
    def _fields(
        self,
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        raise NotImplementedError

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Return:
        object_fields = [
            object_field_from_field(f, types[f.name])
            for f in self._fields(fields, init_vars)
        ]
        return self._object(
            cls,
            sort_by_annotations_position(cls, object_fields, key=lambda f: f.name),
        )

    def _object(self, cls: Type, fields: Sequence[ObjectField]) -> Return:
        return self.object(cls, apply_class_aliaser(cls, fields))

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> Return:
        raise NotImplementedError

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> Return:
        fields = [
            ObjectField(
                name,
                tp,
                name not in defaults,
                annotated_metadata(tp),
                defaults.get(name),
            )
            for name, tp in types.items()
        ]
        return self._object(cls, fields)

    def typed_dict(
        self, cls: Type, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> Return:
        # Fields cannot have Annotated metadata because they would not be available
        # at serialization
        fields = [
            ObjectField(
                name, tp, name in required_keys, default=Undefined, aliased=False
            )
            for name, tp in types.items()
        ]
        return self.object(cls, fields)  # no class aliaser for typed_dict

    def _visit(self, tp: AnyType) -> Return:
        if isinstance(tp, type) and issubclass(tp, ObjectWrapper):
            fields = tp.fields
            if self._generic is not None:
                (wrapped,) = get_args(self._generic)
                if get_args(wrapped):
                    substitution = dict(zip(get_parameters(wrapped), get_args(wrapped)))
                    fields = [
                        replace(f, type=substitute_type_vars(f.type, substitution))
                        for f in fields
                    ]
            return self._object(tp.type, fields)
        return super()._visit(tp)


class DeserializationObjectVisitor(ObjectVisitor[Return]):
    def _fields(
        self,
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        return (*(f for f in fields if f.init), *init_vars)


class SerializationObjectVisitor(ObjectVisitor[Return]):
    def _fields(
        self,
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        return fields


class GetFields(ObjectVisitor[Sequence[ObjectField]]):
    def __init__(self, serialization: bool):
        super().__init__()
        self.serialization = serialization

    def _fields(
        self,
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        return fields if self.serialization else (*fields, *init_vars)

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> Sequence[ObjectField]:
        return fields


@cache
def object_fields(
    tp: AnyType, *, serialization: bool = False
) -> Mapping[str, ObjectField]:
    try:
        return OrderedDict((f.name, f) for f in GetFields(serialization).visit(tp))
    except Unsupported:
        raise TypeError(f"{tp} doesn't have fields")


def object_fields2(obj: Any, serialization: bool = False) -> Mapping[str, ObjectField]:
    return object_fields(
        obj if isinstance(obj, (type, _GenericAlias)) else obj.__class__,
        serialization=serialization,
    )


FieldOrName = Union[str, ObjectField, Field]


def _bad_field(obj: Any) -> NoReturn:
    raise TypeError(
        f"Expected dataclasses.Field/apischema.ObjectField/str, found {obj}"
    )


def check_field_or_name(field_or_name: Any):
    if not isinstance(field_or_name, (str, ObjectField, Field)):
        _bad_field(field_or_name)


def get_field_name(field_or_name: Any) -> str:
    if isinstance(field_or_name, (Field, ObjectField)):
        return field_or_name.name
    elif isinstance(field_or_name, str):
        return field_or_name
    else:
        _bad_field(field_or_name)


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


class AliasGetter:
    def __init__(self, obj: Any):
        self.fields = object_fields2(obj)

    def __getattribute__(self, name: str) -> AliasedStr:
        try:
            return object.__getattribute__(self, "fields")[name].alias
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
