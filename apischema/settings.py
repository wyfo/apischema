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
from apischema.schemas import Schema, default_schema as default_schema_
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


class settings(metaclass=MetaSettings):
    aliaser: Aliaser = lambda s: s
    default_object_fields: Callable[
        [type], Optional[Sequence[ObjectField]]
    ] = default_object_fields_
    default_schema: Callable[[AnyType], Optional[Schema]] = default_schema_
    default_type_name: Callable[[AnyType], Optional[TypeName]] = default_type_name_
    json_schema_version: JsonSchemaVersion = JsonSchemaVersion.DRAFT_2019_09

    class deserialization(metaclass=ResetCache):
        additional_properties: bool = False
        coerce: bool = False
        coercer: Coercer = coerce_
        fall_back_on_default: bool = False
        default_conversion: DefaultConversion = default_deserialization

    class serialization(metaclass=ResetCache):
        check_type: bool = False
        fall_back_on_any: bool = False
        default_conversion: DefaultConversion = default_serialization
        exclude_unset: bool = True
