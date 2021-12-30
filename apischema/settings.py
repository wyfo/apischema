import warnings
from inspect import Parameter
from typing import Any, Callable, Optional, Sequence, Union

from apischema import cache
from apischema.aliases import Aliaser
from apischema.conversions.conversions import DefaultConversion
from apischema.conversions.converters import (
    default_deserialization,
    default_serialization,
)
from apischema.deserialization.coercion import Coercer
from apischema.deserialization.coercion import coerce as coerce_
from apischema.json_schema import JsonSchemaVersion
from apischema.objects import ObjectField
from apischema.objects.fields import default_object_fields as default_object_fields_
from apischema.schemas import Schema
from apischema.serialization import PassThroughOptions
from apischema.type_names import TypeName
from apischema.type_names import default_type_name as default_type_name_
from apischema.types import AnyType
from apischema.utils import CollectionOrPredicate, to_camel_case


class ResetCache(type):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        cache.reset()


class MetaSettings(ResetCache):
    @property
    def camel_case(cls) -> bool:
        raise NotImplementedError

    @camel_case.setter
    def camel_case(cls, value: bool):
        settings.aliaser = to_camel_case if value else lambda s: s

    @property
    def default_schema(cls) -> Callable[[AnyType], Optional[Schema]]:
        warnings.warn(
            "settings.default_schema is deprecated,"
            " use settings.base_schema.type instead",
            DeprecationWarning,
        )
        assert cls is settings
        return cls.base_schema.type  # type: ignore

    @default_schema.setter
    def default_schema(cls, value: Callable[[AnyType], Optional[Schema]]):
        warnings.warn(
            "settings.default_schema is deprecated,"
            " use settings.base_schema.type instead",
            DeprecationWarning,
        )
        assert cls is settings
        cls.base_schema.type = value  # type: ignore


ConstraintError = Union[str, Callable[[Any, Any], str]]


class settings(metaclass=MetaSettings):
    additional_properties: bool = False
    aliaser: Aliaser = lambda s: s
    default_object_fields: Callable[
        [type], Optional[Sequence[ObjectField]]
    ] = default_object_fields_
    default_type_name: Callable[[AnyType], Optional[TypeName]] = default_type_name_
    json_schema_version: JsonSchemaVersion = JsonSchemaVersion.DRAFT_2020_12

    class base_schema:
        field: Callable[[AnyType, str, str], Optional[Schema]] = lambda *_: None
        method: Callable[[AnyType, Callable, str], Optional[Schema]] = lambda *_: None
        parameter: Callable[
            [Callable, Parameter, str], Optional[Schema]
        ] = lambda *_: None
        type: Callable[[AnyType], Optional[Schema]] = lambda *_: None

    class errors:
        minimum: ConstraintError = "less than {} (minimum)"
        maximum: ConstraintError = "greater than {} (maximum)"
        exclusive_minimum: ConstraintError = (
            "less than or equal to {} (exclusiveMinimum)"
        )
        exclusive_maximum: ConstraintError = (
            "greater than or equal to {} (exclusiveMinimum)"
        )
        multiple_of: ConstraintError = "not a multiple of {} (multipleOf)"

        min_length: ConstraintError = "string length lower than {} (minLength)"
        max_length: ConstraintError = "string length greater than {} (maxLength)"
        pattern: ConstraintError = "not matching pattern {} (pattern)"

        min_items: ConstraintError = "item count lower than {} (minItems)"
        max_items: ConstraintError = "item count greater than {} (maxItems)"
        unique_items: ConstraintError = "duplicate items (uniqueItems)"

        min_properties: ConstraintError = "property count lower than {} (minProperties)"
        max_properties: ConstraintError = (
            "property count greater than {} (maxProperties)"
        )

        one_of: ConstraintError = "not one of {} (oneOf)"

        unexpected_property: str = "unexpected property"
        missing_property: str = "missing property"

    class deserialization(metaclass=ResetCache):
        coerce: bool = False
        coercer: Coercer = coerce_
        default_conversion: DefaultConversion = default_deserialization
        fall_back_on_default: bool = False
        no_copy: bool = True
        override_dataclass_constructors = False
        pass_through: CollectionOrPredicate[type] = ()

    class serialization(metaclass=ResetCache):
        check_type: bool = False
        fall_back_on_any: bool = False
        default_conversion: DefaultConversion = default_serialization
        exclude_defaults: bool = False
        exclude_none: bool = False
        exclude_unset: bool = True
        no_copy: bool = True
        pass_through: PassThroughOptions = PassThroughOptions()
