__all__ = ["get_alias", "get_field", "object_fields"]
from dataclasses import (
    Field,
    InitVar,
    MISSING,
    dataclass,
    field,
    make_dataclass,
    replace,
)
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

from apischema.aliases import AliasedStr
from apischema.cache import cache
from apischema.conversions.conversions import Conversions
from apischema.json_schema.schemas import Schema
from apischema.metadata.implem import ConversionMetadata, ValidatorsMetadata, required
from apischema.metadata.keys import (
    ALIAS_METADATA,
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
    PREFIX,
    get_parameters,
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

    def __post_init__(self, default: Any):
        if not self.required and self.default_factory is None:
            if default is MISSING_DEFAULT:
                raise ValueError("Missing default for required ObjectField")
            object.__setattr__(self, "default_factory", lambda: default)

    @property
    def additional_properties(self) -> bool:
        return self.metadata.get(PROPERTIES_METADATA, ...) is None

    @property
    def alias(self) -> AliasedStr:
        return self.metadata.get(ALIAS_METADATA, self.name)

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
    required = (
        REQUIRED_METADATA in metadata
        or field.default is MISSING
        and field.default_factory is MISSING  # type: ignore
    )
    return ObjectField(
        field.name,
        field_type,
        required,
        metadata,
        default=field.default,
        default_factory=field.default_factory,  # type: ignore
    )


def object_field_to_field(field: ObjectField) -> Tuple[str, AnyType, Field]:
    metadata = ChainMap(required, field.metadata) if field.required else field.metadata
    dataclass_field = Field(  # type: ignore
        MISSING, field.default_factory, True, True, None, True, metadata
    )
    return field.name, field.type, dataclass_field


def dataclass_from_fields(name: str, fields: Iterable[ObjectField]) -> type:
    return make_dataclass(name, map(object_field_to_field, fields))


T = TypeVar("T")

OBJECT_WRAPPER_ATTR = f"{PREFIX}object_wrapper"


@dataclass
class ObjectWrapper(Generic[T]):
    fields: ClassVar[Sequence[ObjectField]]
    wrapped: T


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
        return self.object(
            cls,
            sort_by_annotations_position(cls, object_fields, key=lambda f: f.name),
        )

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
                name in defaults,
                annotated_metadata(tp),
                defaults.get(name),
            )
            for name, tp in types.items()
        ]
        return self.object(cls, fields)

    def typed_dict(
        self, cls: Type, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> Return:
        # Fields cannot have Annotated metadata because they would not be available
        # at serialization
        fields = [
            ObjectField(name, tp, name in required_keys) for name, tp in types.items()
        ]
        return self.object(cls, fields)

    def visit(self, tp: AnyType) -> Return:
        origin = get_origin(tp)
        if origin is not None and issubclass(origin, ObjectWrapper):
            (wrapped,) = get_args(tp)
            fields = origin.fields
            wrapped_origin = get_origin(wrapped)
            if wrapped_origin is not None:
                substitution = dict(
                    zip(get_parameters(wrapped_origin), get_args(wrapped))
                )
                fields2 = [
                    replace(f, type=substitute_type_vars(f.type, substitution))
                    for f in fields
                ]
                _generic = self._generic
                self._generic = wrapped
                try:
                    return self.object(wrapped_origin, fields2)
                finally:
                    self._generic = _generic
            else:
                return self.object(wrapped, fields)
        else:
            return super().visit(tp)


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
    def _fields(
        self,
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        return (*fields, *init_vars)

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> Sequence[ObjectField]:
        return fields


@cache
def object_fields(tp: AnyType) -> Mapping[str, ObjectField]:
    try:
        return OrderedDict((f.name, f) for f in GetFields().visit(tp))
    except Unsupported:
        raise TypeError(f"{tp} doesn't have fields")


def object_fields2(obj: Any) -> Mapping[str, ObjectField]:
    return object_fields(
        obj if isinstance(obj, (type, _GenericAlias)) else obj.__class__
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
