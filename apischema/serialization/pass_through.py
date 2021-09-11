from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import Any, Callable, Collection, Mapping, Optional, Sequence, Type, Union

from apischema.aliases import Aliaser
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.visitor import (
    RecursiveConversionsVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.fields import support_fields_set
from apischema.objects import AliasedStr, ObjectField
from apischema.objects.visitor import SerializationObjectVisitor
from apischema.serialization.serialized_methods import get_serialized_methods
from apischema.types import AnyType
from apischema.typing import is_typed_dict
from apischema.utils import Lazy, as_predicate, get_origin_or_type, opt_or


@dataclass(frozen=True)
class PassThroughOptions:
    @dataclass(frozen=True)
    class Dataclass:
        aliaser: bool = False
        aliased_fields: bool = False
        flattened_fields: bool = False
        properties_fields: bool = False
        skipped_fields: bool = False
        skipped_if_fields: bool = False

    any: bool = False
    collections: bool = False
    dataclasses: Union[bool, "PassThroughOptions.Dataclass"] = False
    enums: bool = False
    types: Union[Collection[AnyType], Callable[[AnyType], bool]] = ()

    def __post_init__(self):
        object.__setattr__(self, "types", as_predicate(self.types))

    @property
    def dataclass_options(self) -> "Optional[PassThroughOptions.Dataclass]":
        if isinstance(self.dataclasses, PassThroughOptions.Dataclass):
            return self.dataclasses
        elif self.dataclasses:
            return PassThroughOptions.Dataclass()
        else:
            return None


class Recursive(Exception):
    pass


class PassThroughVisitor(
    RecursiveConversionsVisitor[Serialization, bool],
    SerializationVisitor[bool],
    SerializationObjectVisitor[bool],
):
    def __init__(
        self,
        additional_properties: bool,
        aliaser: Aliaser,
        default_conversion: DefaultConversion,
        exclude_defaults: bool,
        exclude_none: bool,
        exclude_unset: bool,
        options: PassThroughOptions,
    ):
        super().__init__(default_conversion)
        self.additional_properties = additional_properties
        self.aliaser = aliaser
        self.exclude_defaults = exclude_defaults
        self.exclude_none = exclude_none
        self.exclude_unset = exclude_unset
        self.options = options

    def _recursive_result(self, lazy: Lazy[bool]) -> bool:
        # Recursive fields are handled as passing through. In fact, if all fields are
        # passing through too, the recursive class will be pass through too. Otherwise,
        # if one other field is not passing through, the recursive class will not be
        # passing through. So recursive fields have no impact.
        # If the recursion is not direct, that's still correct: the nested class will be
        # passing through depending of its other fields.
        return True

    def any(self) -> bool:
        return self.options.any

    def collection(self, cls: Type[Collection], value_type: AnyType) -> bool:
        return (
            self.options.collections or issubclass(cls, (list, tuple))
        ) and self.visit(value_type)

    def enum(self, cls: Type[Enum]) -> bool:
        return self.options.enums or issubclass(cls, (int, str))

    def literal(self, values: Sequence[Any]) -> bool:
        return self.options.enums or all(isinstance(v, (int, str)) for v in values)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> bool:
        return (
            (self.options.collections or issubclass(cls, dict))
            and self.visit(key_type)
            and self.visit(value_type)
        )

    def _object(self, tp: AnyType, fields: Sequence[ObjectField]) -> bool:
        cls = get_origin_or_type(tp)
        support_skipped = not any(self._skip_field(f) for f in fields) or (
            is_dataclass(cls)
            and self.options.dataclass_options is not None
            and self.options.dataclass_options.skipped_fields
        )
        return (
            support_skipped
            and not get_serialized_methods(tp)
            and super()._object(tp, fields)
        )

    def object(self, tp: AnyType, fields: Sequence[ObjectField]) -> bool:
        cls = get_origin_or_type(tp)
        if is_dataclass(cls) and self.options.dataclass_options is not None:
            if self.exclude_unset and support_fields_set(cls):
                return False
            dataclass_options = self.options.dataclass_options
        elif (
            is_typed_dict(cls)
            and self.options.collections
            and not self.additional_properties
        ):
            dataclass_options = PassThroughOptions.Dataclass()
        else:
            return False
        return all(
            (dataclass_options.aliaser or self.aliaser(field.alias) == field.alias)
            and (dataclass_options.aliased_fields or field.alias == field.name)
            and (dataclass_options.flattened_fields or not field.flattened)
            and (
                dataclass_options.properties_fields
                or not (field.pattern_properties or field.additional_properties)
            )
            and (
                dataclass_options.skipped_if_fields
                or field.skip_if(self.exclude_defaults, self.exclude_none) is None
            )
            and self.visit_with_conv(field.type, field.serialization)
            for field in fields
        )

    def primitive(self, cls: Type) -> bool:
        return True

    def tuple(self, types: Sequence[AnyType]) -> bool:
        return all(map(self.visit, types))

    def union(self, alternatives: Sequence[AnyType]) -> bool:
        return all(self._union_results(alternatives))

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Serialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> bool:
        return False

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Serialization],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> bool:
        return not dynamic and (
            as_predicate(self.options.types)(tp)
            or super().visit_conversion(tp, conversion, dynamic, next_conversion)
        )

    def visit(self, tp: AnyType) -> bool:
        return tp is not AliasedStr and super().visit(tp)


@lru_cache()
def pass_through(
    tp: AnyType,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    conversions: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_defaults: bool = None,
    exclude_none: bool = None,
    exclude_unset: bool = None,
    options: PassThroughOptions = None,
) -> bool:
    from apischema import settings

    return PassThroughVisitor(
        opt_or(additional_properties, settings.additional_properties),
        opt_or(aliaser, settings.aliaser),
        opt_or(default_conversion, settings.serialization.default_conversion),
        opt_or(exclude_defaults, settings.serialization.exclude_defaults),
        opt_or(exclude_none, settings.serialization.exclude_none),
        opt_or(exclude_unset, settings.serialization.exclude_unset),
        opt_or(options, settings.serialization.pass_through),
    ).visit_with_conv(tp, conversions)
