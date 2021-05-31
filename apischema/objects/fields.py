from dataclasses import Field, InitVar, MISSING, dataclass, field
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Mapping,
    NoReturn,
    Optional,
    Pattern,
    Sequence,
    TYPE_CHECKING,
    Union,
    cast,
)

from apischema.conversions.conversions import Conversions
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
from apischema.objects.utils import AliasedStr
from apischema.types import AnyType, ChainMap
from apischema.typing import get_args, is_annotated, type_dict_wrapper
from apischema.utils import LazyValue, empty_dict

if TYPE_CHECKING:
    from apischema.schemas import Schema
    from apischema.schemas.annotations import Annotations
    from apischema.schemas.constraints import Constraints
    from apischema.validation.validators import Validator


class FieldKind(Enum):
    NORMAL = auto()
    READ_ONLY = auto()
    WRITE_ONLY = auto()


# Cannot reuse MISSING for dataclass field because it would be interpreted as no default
MISSING_DEFAULT = object()


@dataclass(frozen=True)
class ObjectField:
    name: str
    type: AnyType
    required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=lambda: empty_dict)
    default: InitVar[Any] = MISSING_DEFAULT
    default_factory: Optional[Callable[[], Any]] = None
    kind: FieldKind = FieldKind.NORMAL

    def __post_init__(self, default: Any):
        if REQUIRED_METADATA in self.full_metadata:
            object.__setattr__(self, "required", True)
        if self.default_factory is MISSING:
            object.__setattr__(self, "default_factory", None)
        if not self.required and self.default_factory is None:
            if default is MISSING_DEFAULT:
                raise ValueError("Missing default for required ObjectField")
            object.__setattr__(self, "default_factory", LazyValue(default))

    @property
    def full_metadata(self) -> Mapping[str, Any]:
        if not is_annotated(self.type):
            return self.metadata
        return ChainMap(
            self.metadata,
            *(
                arg
                for arg in reversed(get_args(self.type)[1:])
                if isinstance(arg, Mapping)
            ),
        )

    @property
    def additional_properties(self) -> bool:
        return self.full_metadata.get(PROPERTIES_METADATA, ...) is None

    @property
    def alias(self) -> str:
        return AliasedStr(self.full_metadata.get(ALIAS_METADATA, self.name))

    @property
    def override_alias(self) -> bool:
        return ALIAS_NO_OVERRIDE_METADATA not in self.full_metadata

    @property
    def _conversion(self) -> Optional[ConversionMetadata]:
        return self.metadata.get(CONVERSION_METADATA, None)

    @property
    def default_as_set(self) -> bool:
        return DEFAULT_AS_SET_METADATA in self.full_metadata

    @property
    def default_fallback(self) -> bool:
        return DEFAULT_FALLBACK_METADATA in self.full_metadata

    @property
    def deserialization(self) -> Optional[Conversions]:
        conversion = self._conversion
        return conversion.deserialization if conversion is not None else None

    @property
    def merged(self) -> bool:
        return MERGED_METADATA in self.full_metadata

    @property
    def post_init(self) -> bool:
        return POST_INIT_METADATA in self.full_metadata

    @property
    def pattern_properties(self) -> Union[Pattern, "ellipsis", None]:  # noqa: F821
        return self.full_metadata.get(PROPERTIES_METADATA, None)

    @property
    def schema(self) -> Optional["Schema"]:
        return self.metadata.get(SCHEMA_METADATA, None)

    @property
    def annotations(self) -> Optional["Annotations"]:
        return self.schema.annotations if self.schema is not None else None

    @property
    def constraints(self) -> Optional["Constraints"]:
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


_class_fields: Dict[type, Callable[[], Sequence[ObjectField]]] = type_dict_wrapper({})


def set_object_fields(
    cls: type,
    fields: Union[Iterable[ObjectField], Callable[[], Sequence[ObjectField]], None],
):
    if fields is None:
        _class_fields.pop(cls, ...)
    elif callable(fields):
        _class_fields[cls] = fields
    else:
        _class_fields[cls] = lambda fields=tuple(fields): fields  # type: ignore


def default_object_fields(cls: type) -> Optional[Sequence[ObjectField]]:
    return _class_fields[cls]() if cls in _class_fields else None
