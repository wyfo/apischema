from typing import AbstractSet, Any, Sequence, Type

from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dataclasses.cache import (
    Field,
    FieldCache,
    get_deserialization_fields,
    get_serialization_fields,
)
from apischema.fields import fields
from apischema.types import AnyType, Skip, SkipSchema, Skipped
from apischema.visitor import Arg, Return


class SchemaVisitor(ConversionsVisitor[Conv, Arg, Return]):
    def annotated(self, cls: AnyType, annotations: Sequence[Any], arg: Arg) -> Return:
        for annotation in reversed(annotations):
            if annotation in {Skip, SkipSchema}:
                raise Skipped
        return self._annotated(cls, annotations, arg)

    def _annotated(self, cls: AnyType, annotations: Sequence[Any], arg: Arg) -> Return:
        return self.visit(cls, arg)

    @staticmethod
    def _dataclass_fields(cls: Type) -> FieldCache:
        raise NotImplementedError()

    _field_type: Any
    _field_conversions: Any

    def _field_visit(self, field: Field, arg: Arg) -> Return:
        conversions_save = self.conversions
        self.conversions = getattr(field, self._field_conversions.name)
        try:
            return self.visit(getattr(field, self._field_type.name), arg)
        finally:
            self.conversions = conversions_save

    _field_required_by: Any

    @classmethod
    def _required_by(cls, field: Field) -> AbstractSet[str]:
        return getattr(field, cls._field_required_by.name)

    @staticmethod
    def _override_arg(cls: AnyType, arg: Arg) -> Arg:  # type: ignore
        return arg

    def _union_arg(self, cls: AnyType, arg: Arg) -> Arg:  # type: ignore
        raise NotImplementedError()

    def _union_result(self, results: Sequence[Return], arg: Arg) -> Return:
        raise NotImplementedError()

    def union(self, alternatives: Sequence[AnyType], arg: Arg) -> Return:
        results = []
        for cls in alternatives:
            try:
                results.append(self.visit(cls, self._union_arg(cls, arg)))
            except Skipped:
                pass
        return self._union_result(results, arg)

    def _is_conversion(self, cls: AnyType) -> bool:
        # In 3.6, GenericAlias are classes with mro
        if getattr(cls, "__origin__", None) is not None:
            return False
        try:
            return bool(self.is_conversion(cls, self.conversions))
        except Exception:
            return False


class DeserializationSchemaVisitor(
    DeserializationVisitor[Arg, Return], SchemaVisitor[Deserialization, Arg, Return],
):
    def visit_conversion(
        self, cls: Type, conversion: Deserialization, arg: Arg
    ) -> Return:
        assert conversion
        results = []
        conversions = self.conversions
        for cls_, (converter, self.conversions) in conversion.items():
            try:
                results.append(self.visit(cls_, self._union_arg(cls, arg)))
            except Skipped:
                raise TypeError("Deserialization type cannot be skipped")
            finally:
                self.conversions = conversions
        return self._union_result(results, self._override_arg(cls, arg))

    _dataclass_fields = staticmethod(get_deserialization_fields)  # type: ignore
    _field_type = fields(Field).deserialization_type
    _field_conversions = fields(Field).deserialization_conversions
    _field_required_by = fields(Field).deserialization_required_by


class SerializationSchemaVisitor(
    SerializationVisitor[Arg, Return], SchemaVisitor[Serialization, Arg, Return],
):
    def visit_conversion(
        self, cls: Type, conversion: Serialization, arg: Arg
    ) -> Return:
        conversions = self.conversions
        target, (converter, self.conversions) = conversion
        try:
            return self.visit(target, self._override_arg(cls, arg))
        finally:
            self.conversions = conversions

    _dataclass_fields = staticmethod(get_serialization_fields)  # type: ignore
    _field_type = fields(Field).serialization_type
    _field_conversions = fields(Field).serialization_conversions
    _field_required_by = fields(Field).serialization_required_by
