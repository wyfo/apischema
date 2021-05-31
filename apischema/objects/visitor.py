from dataclasses import Field, MISSING, replace
from typing import Any, Collection, Mapping, Optional, Sequence, Tuple, Type

from apischema.aliases import Aliaser, get_class_aliaser
from apischema.conversions.conversions import Conversions
from apischema.metadata.keys import ALIAS_METADATA, SKIP_METADATA
from apischema.objects.fields import FieldKind, MISSING_DEFAULT, ObjectField
from apischema.types import AnyType, Undefined
from apischema.typing import get_args
from apischema.utils import (
    get_args2,
    get_origin2,
    get_origin_or_type2,
    get_parameters,
    substitute_type_vars,
)
from apischema.visitor import Return, Visitor


def object_field_from_field(
    field: Field, field_type: AnyType, init_var: bool
) -> ObjectField:
    required = field.default is MISSING and field.default_factory is MISSING  # type: ignore
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
        default_factory=field.default_factory,  # type: ignore
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


def remove_annotations(tp: AnyType) -> AnyType:
    origin = get_origin2(tp)
    return origin[get_args2(tp)] if origin is not None else get_origin_or_type2(tp)


class ObjectVisitor(Visitor[Return]):
    _dataclass_field_kind_filtered: Optional[FieldKind] = None

    def _field_conversion(self, field: ObjectField) -> Optional[Conversions]:
        return NotImplementedError

    def _object(
        self, cls: Type, fields: Sequence[ObjectField], class_aliasing: bool = True
    ) -> Return:
        fields = [field for field in fields if SKIP_METADATA not in field.metadata]
        if class_aliasing:
            aliaser = get_class_aliaser(cls)
            if aliaser is not None:
                fields = [_override_alias(f, aliaser) for f in fields]
        return self.object(cls, fields)

    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Return:
        by_name = {
            f.name: object_field_from_field(f, types[f.name], init_var)
            for field_group, init_var in [(fields, False), (init_vars, True)]
            for f in field_group
        }
        object_fields = [
            by_name[name]
            for name in types
            if name in by_name
            and by_name[name].kind != self._dataclass_field_kind_filtered
        ]
        return self._object(cls, object_fields)

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> Return:
        raise NotImplementedError

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> Return:
        fields = [
            ObjectField(name, tp, name not in defaults, default=defaults.get(name))
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
                name,
                remove_annotations(tp),
                name in required_keys,
                default=Undefined,
                aliased=False,
            )
            for name, tp in types.items()
        ]
        return self._object(cls, fields, class_aliasing=False)

    def unsupported(self, tp: AnyType) -> Return:
        from apischema import settings

        if isinstance(tp, type):
            fields = settings.default_object_fields(tp)
            if fields is not None:
                if self._generic is not None:
                    sub = dict(
                        zip(get_parameters(self._generic), get_args(self._generic))
                    )
                    fields = [
                        replace(f, type=substitute_type_vars(f.type, sub))
                        for f in fields
                    ]
                return self._object(tp, fields)
        return super().unsupported(tp)


class DeserializationObjectVisitor(ObjectVisitor[Return]):
    _dataclass_field_kind_filtered = FieldKind.READ_ONLY

    @staticmethod
    def _field_conversion(field: ObjectField) -> Optional[Conversions]:
        return field.deserialization


class SerializationObjectVisitor(ObjectVisitor[Return]):
    _dataclass_field_kind_filtered = FieldKind.WRITE_ONLY

    @staticmethod
    def _field_conversion(field: ObjectField) -> Optional[Conversions]:
        return field.serialization
