from dataclasses import MISSING, Field
from typing import Any, Collection, Mapping, Optional, Sequence

from apischema.aliases import Aliaser, get_class_aliaser
from apischema.conversions.conversions import AnyConversion
from apischema.dataclasses import replace
from apischema.metadata.keys import ALIAS_METADATA
from apischema.objects.fields import MISSING_DEFAULT, FieldKind, ObjectField
from apischema.types import AnyType, Undefined
from apischema.typing import get_args
from apischema.utils import get_origin_or_type, get_parameters, substitute_type_vars
from apischema.visitor import Result, Visitor


def object_field_from_field(
    field: Field, field_type: AnyType, init_var: bool
) -> ObjectField:
    required = field.default is MISSING and field.default_factory is MISSING
    if init_var:
        kind = FieldKind.WRITE_ONLY
    elif not field.init:
        kind = FieldKind.READ_ONLY
    else:
        kind = FieldKind.NORMAL
    return ObjectField(
        field.name,
        field_type,
        required,
        field.metadata,
        default=field.default,
        default_factory=field.default_factory,
        kind=kind,
    )


def _override_alias(field: ObjectField, aliaser: Aliaser) -> ObjectField:
    if field.override_alias:
        return replace(
            field,
            metadata={**field.metadata, ALIAS_METADATA: aliaser(field.alias)},
            default=MISSING_DEFAULT,
        )
    else:
        return field


class ObjectVisitor(Visitor[Result]):
    _field_kind_filtered: Optional[FieldKind] = None

    def _field_conversion(self, field: ObjectField) -> Optional[AnyConversion]:
        raise NotImplementedError

    def _skip_field(self, field: ObjectField) -> bool:
        raise NotImplementedError

    @staticmethod
    def _default_fields(cls: type) -> Optional[Sequence[ObjectField]]:
        from apischema import settings

        return settings.default_object_fields(cls)

    def _override_fields(
        self, tp: AnyType, fields: Sequence[ObjectField]
    ) -> Sequence[ObjectField]:

        origin = get_origin_or_type(tp)
        if isinstance(origin, type):
            default_fields = self._default_fields(origin)
            if default_fields is not None:
                if get_args(tp):
                    sub = dict(zip(get_parameters(origin), get_args(tp)))
                    default_fields = [
                        replace(f, type=substitute_type_vars(f.type, sub))
                        for f in default_fields
                    ]
                return default_fields
        return fields

    def _object(self, tp: AnyType, fields: Sequence[ObjectField]) -> Result:
        fields = [f for f in fields if not self._skip_field(f)]
        aliaser = get_class_aliaser(get_origin_or_type(tp))
        if aliaser is not None:
            fields = [_override_alias(f, aliaser) for f in fields]
        return self.object(tp, fields)

    def dataclass(
        self,
        tp: AnyType,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Result:
        by_name = {
            f.name: object_field_from_field(f, types[f.name], init_var)
            for field_group, init_var in [(fields, False), (init_vars, True)]
            for f in field_group
        }
        object_fields = [
            by_name[name]
            for name in types
            if name in by_name and by_name[name].kind != self._field_kind_filtered
        ]
        return self._object(tp, self._override_fields(tp, object_fields))

    def object(self, tp: AnyType, fields: Sequence[ObjectField]) -> Result:
        raise NotImplementedError

    def named_tuple(
        self, tp: AnyType, types: Mapping[str, AnyType], defaults: Mapping[str, Any]
    ) -> Result:
        fields = [
            ObjectField(name, type_, name not in defaults, default=defaults.get(name))
            for name, type_ in types.items()
        ]
        return self._object(tp, self._override_fields(tp, fields))

    def typed_dict(
        self, tp: AnyType, types: Mapping[str, AnyType], required_keys: Collection[str]
    ) -> Result:
        fields = [
            ObjectField(name, type_, name in required_keys, default=Undefined)
            for name, type_ in types.items()
        ]
        return self._object(tp, self._override_fields(tp, fields))

    def unsupported(self, tp: AnyType) -> Result:
        dummy: list = []
        fields = self._override_fields(tp, dummy)
        return super().unsupported(tp) if fields is dummy else self._object(tp, fields)


class DeserializationObjectVisitor(ObjectVisitor[Result]):
    _field_kind_filtered = FieldKind.READ_ONLY

    @staticmethod
    def _field_conversion(field: ObjectField) -> Optional[AnyConversion]:
        return field.deserialization

    @staticmethod
    def _skip_field(field: ObjectField) -> bool:
        return field.skip.deserialization


class SerializationObjectVisitor(ObjectVisitor[Result]):
    _field_kind_filtered = FieldKind.WRITE_ONLY

    @staticmethod
    def _field_conversion(field: ObjectField) -> Optional[AnyConversion]:
        return field.serialization

    @staticmethod
    def _skip_field(field: ObjectField) -> bool:
        return field.skip.serialization
