import warnings
from inspect import Parameter
from typing import Callable, Optional, Sequence

from apischema import cache
from apischema.aliases import Aliaser
from apischema.conversions.conversions import DefaultConversion
from apischema.conversions.converters import (
    default_deserialization,
    default_serialization,
)
from apischema.deserialization.coercion import Coercer, coerce as coerce_
from apischema.json_schema import JsonSchemaVersion
from apischema.objects import ObjectField
from apischema.objects.fields import default_object_fields as default_object_fields_
from apischema.schemas import Schema
from apischema.serialization import PassThroughOptions
from apischema.type_names import TypeName, default_type_name as default_type_name_
from apischema.types import AnyType
from apischema.utils import to_camel_case


class ResetCache(type):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        cache.reset()


class MetaSettings(ResetCache):
    @property
    def camel_case(self) -> bool:
        raise NotImplementedError

    @camel_case.setter
    def camel_case(self, value: bool):
        settings.aliaser = to_camel_case if value else lambda s: s

    def __setattr__(self, name, value):
        if name == "default_schema" and not isinstance(value, ResetCache):
            warnings.warn(
                "settings.default_schema is deprecated,"
                " use settings.base_schema.type instead",
                DeprecationWarning,
            )
            assert self is settings
            self.base_schema.type = value  # type: ignore
        else:
            super().__setattr__(name, value)


class settings(metaclass=MetaSettings):
    additional_properties: bool = False
    aliaser: Aliaser = lambda s: s
    default_object_fields: Callable[
        [type], Optional[Sequence[ObjectField]]
    ] = default_object_fields_
    default_schema: Callable[[AnyType], Optional[Schema]] = lambda *_: None
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
        minimum: str = "less than {constraint} (minimum)"
        maximum: str = "greater than {constraint} (maximum)"
        exclusive_minimum: str = "less than or equal to {constraint} (exclusiveMinimum)"
        exclusive_maximum: str = (
            "greater than or equal to {constraint} (exclusiveMinimum)"
        )
        multiple_of: str = "not a multiple of {constraint} (multipleOf)"

        min_length: str = "string length lower than {constraint} (minLength)"
        max_length: str = "string length greater than {constraint} (maxLength)"
        pattern: str = 'not matching pattern "{constraint}" (pattern)'

        min_items: str = "item count lower than {constraint} (minItems)"
        max_items: str = "item count greater than {constraint} (maxItems)"
        unique_items: str = "duplicate items (uniqueItems)"

        min_properties: str = "property count lower than {constraint} (minProperties)"
        max_properties: str = "property count greater than {constraint} (maxProperties)"

        one_of: str = "not one of {constraint} (oneOf)"
        unexpected_property: str = "unexpected property"
        missing_property: str = "missing property"

    class deserialization(metaclass=ResetCache):
        coerce: bool = False
        coercer: Coercer = coerce_
        default_conversion: DefaultConversion = default_deserialization
        fall_back_on_default: bool = False

    class serialization(metaclass=ResetCache):
        check_type: bool = False
        fall_back_on_any: bool = False
        default_conversion: DefaultConversion = default_serialization
        exclude_defaults: bool = False
        exclude_none: bool = False
        exclude_unset: bool = True
        pass_through: PassThroughOptions = PassThroughOptions()
