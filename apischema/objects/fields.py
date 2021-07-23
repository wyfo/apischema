from dataclasses import Field, InitVar, MISSING, dataclass, field
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    NoReturn,
    Optional,
    Pattern,
    Sequence,
    TYPE_CHECKING,
    Union,
    cast,
)

from apischema.cache import CacheAwareDict
from apischema.conversions.conversions import AnyConversion
from apischema.metadata.implem import (
    ConversionMetadata,
    SkipMetadata,
    ValidatorsMetadata,
)
from apischema.metadata.keys import (
    ALIAS_METADATA,
    ALIAS_NO_OVERRIDE_METADATA,
    CONVERSION_METADATA,
    DEFAULT_AS_SET_METADATA,
    FALL_BACK_ON_DEFAULT_METADATA,
    FLATTEN_METADATA,
    NONE_AS_UNDEFINED_METADATA,
    POST_INIT_METADATA,
    PROPERTIES_METADATA,
    REQUIRED_METADATA,
    SCHEMA_METADATA,
    SKIP_METADATA,
    VALIDATORS_METADATA,
)
from apischema.types import AnyType, ChainMap, NoneType, Undefined, UndefinedType
from apischema.typing import get_args, is_annotated
from apischema.utils import (
    LazyValue,
    empty_dict,
    get_args2,
    is_union_of,
    keep_annotations,
    merge_opts,
)

if TYPE_CHECKING:
    from apischema.schemas import Schema
    from apischema.validation.validators import Validator


class FieldKind(Enum):
    NORMAL = auto()
    READ_ONLY = auto()
    WRITE_ONLY = auto()


# Cannot reuse MISSING for dataclass field because it would be interpreted as no default
MISSING_DEFAULT = object()


@merge_opts
def merge_skip_if(
    s1: Callable[[Any], Any], s2: Callable[[Any], Any]
) -> Callable[[Any], Any]:
    def merged(obj) -> Any:
        return s1(obj) or s2(obj)

    return merged


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
                raise ValueError("Missing default for non-required ObjectField")
            object.__setattr__(self, "default_factory", LazyValue(default))
        if self.none_as_undefined and is_union_of(self.type, NoneType):
            new_type = Union[tuple(a for a in get_args2(self.type) if a != NoneType)]  # type: ignore
            object.__setattr__(self, "type", keep_annotations(new_type, self.type))

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
        return self.full_metadata.get(ALIAS_METADATA, self.name)

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
    def deserialization(self) -> Optional[AnyConversion]:
        conversion = self._conversion
        return conversion.deserialization if conversion is not None else None

    @property
    def fall_back_on_default(self) -> bool:
        return FALL_BACK_ON_DEFAULT_METADATA in self.full_metadata

    @property
    def flattened(self) -> bool:
        return FLATTEN_METADATA in self.full_metadata

    def get_default(self) -> Any:
        if self.required:
            raise RuntimeError("Field is required")
        assert self.default_factory is not None
        return self.default_factory()  # type: ignore

    @property
    def is_aggregate(self) -> bool:
        return (
            self.flattened
            or self.additional_properties
            or self.pattern_properties is not None
        )

    @property
    def none_as_undefined(self):
        return NONE_AS_UNDEFINED_METADATA in self.full_metadata

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
    def serialization(self) -> Optional[AnyConversion]:
        conversion = self._conversion
        return conversion.serialization if conversion is not None else None

    @property
    def skip(self) -> SkipMetadata:
        return self.metadata.get(SKIP_METADATA, SkipMetadata())

    def skip_if(
        self, default: bool = False, none: bool = False
    ) -> Optional[Callable[[Any], Any]]:
        skip_if = self.skip.serialization_if
        if self.default_factory is not None and (
            self.skip.serialization_default or default
        ):
            default = self.default_factory()  # type: ignore
            skip_if = merge_skip_if(skip_if, lambda obj: obj == default)
        if is_union_of(self.type, UndefinedType):
            skip_if = merge_skip_if(skip_if, lambda obj: obj is Undefined)
        if self.none_as_undefined or none:
            skip_if = merge_skip_if(skip_if, lambda obj: obj is None)
        return skip_if

    @property
    def validators(self) -> Sequence["Validator"]:
        if VALIDATORS_METADATA in self.metadata:
            return cast(
                ValidatorsMetadata, self.metadata[VALIDATORS_METADATA]
            ).validators
        else:
            return ()


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


_class_fields: MutableMapping[
    type, Callable[[], Sequence[ObjectField]]
] = CacheAwareDict({})


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
