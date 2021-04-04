from dataclasses import Field, MISSING, replace
from typing import Any, Collection, Iterable, Mapping, Optional, Sequence, Tuple, Type

from apischema.aliases import Aliaser, get_class_aliaser
from apischema.conversions.conversions import Conversions
from apischema.metadata.keys import ALIAS_METADATA, REQUIRED_METADATA, SKIP_METADATA
from apischema.objects.conversions import ObjectWrapper
from apischema.objects.fields import MISSING_DEFAULT, ObjectField
from apischema.objects.utils import annotated_metadata
from apischema.types import AnyType
from apischema.typing import get_args, get_origin
from apischema.utils import (
    Undefined,
    get_origin_or_type,
    get_parameters,
    sort_by_annotations_position,
    substitute_type_vars,
)
from apischema.visitor import Return, Visitor


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


def _override_alias(field: ObjectField, aliaser: Aliaser) -> ObjectField:
    if field.override_alias:
        return replace(
            field,
            metadata={**field.metadata, ALIAS_METADATA: aliaser(field.alias)},
            default=MISSING_DEFAULT,
        )
    else:
        return field


def _apply_class_aliaser(
    cls: Type, fields: Sequence[ObjectField]
) -> Sequence[ObjectField]:
    aliaser = get_class_aliaser(cls)
    return fields if aliaser is None else [_override_alias(f, aliaser) for f in fields]


class ObjectVisitor(Visitor[Return]):
    def _fields(
        self,
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        raise NotImplementedError

    def _field_conversion(self, field: ObjectField) -> Optional[Conversions]:
        return NotImplementedError

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
            class_aliasing=True,
        )

    def _object(
        self, cls: Type, fields: Sequence[ObjectField], class_aliasing: bool
    ) -> Return:
        fields = [field for field in fields if SKIP_METADATA not in field.metadata]
        return self.object(
            cls, _apply_class_aliaser(cls, fields) if class_aliasing else fields
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
                name not in defaults,
                annotated_metadata(tp),
                defaults.get(name),
            )
            for name, tp in types.items()
        ]
        return self._object(cls, fields, class_aliasing=True)

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
        return self._object(cls, fields, class_aliasing=False)

    def visit(self, tp: AnyType) -> Return:
        origin = get_origin(tp)
        if isinstance(origin, type) and issubclass(origin, ObjectWrapper):
            fields = origin.fields
            (wrapped,) = get_args(tp)
            assert get_origin_or_type(wrapped) == origin.type
            if get_args(wrapped):
                substitution = dict(zip(get_parameters(wrapped), get_args(wrapped)))
                fields = [
                    replace(f, type=substitute_type_vars(f.type, substitution))
                    for f in fields
                ]
            return self._object(origin.type, fields, class_aliasing=True)
        else:
            return super().visit(tp)


class DeserializationObjectVisitor(ObjectVisitor[Return]):
    @staticmethod
    def _fields(
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        return (*(f for f in fields if f.init), *init_vars)

    @staticmethod
    def _field_conversion(field: ObjectField) -> Optional[Conversions]:
        return field.deserialization


class SerializationObjectVisitor(ObjectVisitor[Return]):
    @staticmethod
    def _fields(
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterable[Field]:
        return fields

    @staticmethod
    def _field_conversion(field: ObjectField) -> Optional[Conversions]:
        return field.serialization
