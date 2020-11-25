from dataclasses import Field
from typing import Iterable, Mapping, Optional, Sequence, Tuple, Type

from apischema.conversions.metadata import get_field_conversions
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dataclass_utils import (
    Requirements,
    get_requiring,
)
from apischema.metadata.keys import SKIP_METADATA
from apischema.resolvers import Resolver, get_resolvers
from apischema.skip import filter_skipped
from apischema.types import AnyType
from apischema.visitor import Return


class SchemaVisitor(ConversionsVisitor[Conv, Return]):
    def _dataclass_fields_(
        self, fields: Sequence[Field], init_vars: Sequence[Field]
    ) -> Iterable[Field]:
        raise NotImplementedError()

    def _dataclass_fields(
        self, fields: Sequence[Field], init_vars: Sequence[Field]
    ) -> Sequence[Field]:
        return [
            f
            for f in self._dataclass_fields_(fields, init_vars)
            if SKIP_METADATA not in f.metadata
        ]

    def _field_conversions(
        self, field: Field, field_type: AnyType
    ) -> Tuple[AnyType, Optional[Conversions]]:
        raise NotImplementedError()

    def _visit_field_(self, field: Field, field_type: AnyType) -> Return:
        return self.visit(field_type)

    def _visit_field(self, field: Field, field_type: AnyType) -> Return:
        field_type, conversions = self._field_conversions(field, field_type)
        with self._replace_conversions(conversions):
            return self._visit_field_(field, field_type)

    def _dependent_required(self, cls: Type) -> Requirements:
        raise NotImplementedError()

    def _resolvers(self, cls: Type) -> Mapping[str, Resolver]:
        raise NotImplementedError()

    def union(self, alternatives: Sequence[AnyType]) -> Return:
        return self._union_result(
            map(self.visit, filter_skipped(alternatives, schema_only=True))
        )


class DeserializationSchemaVisitor(
    DeserializationVisitor[Return], SchemaVisitor[Deserialization, Return]
):
    def visit_conversion(self, cls: AnyType, conversion: Deserialization) -> Return:
        return self._union_result(
            [
                self.visit_with_conversions(source, conversions)
                for source, (_, conversions) in conversion.items()
            ]
        )

    @staticmethod
    def _dataclass_fields_(
        fields: Sequence[Field], init_vars: Sequence[Field]
    ) -> Sequence[Field]:
        return (*(f for f in fields if f.init), *init_vars)

    @staticmethod
    def _field_conversions(
        field: Field, field_type: AnyType
    ) -> Tuple[AnyType, Optional[Conversions]]:
        conversions = get_field_conversions(field, field_type)
        if conversions is None:
            return field_type, None
        elif conversions.deserializer is None:
            return field_type, conversions.deserialization
        else:
            type_ = next(iter(conversions.deserialization_conversion(field_type)))
            return type_, conversions.deserialization

    def _dependent_required(self, cls: Type) -> Requirements:
        return get_requiring(cls)[0]

    def _resolvers(self, cls: Type) -> Mapping[str, Resolver]:
        return {}


class SerializationSchemaVisitor(
    SerializationVisitor[Return], SchemaVisitor[Serialization, Return]
):
    def visit_conversion(self, cls: AnyType, conversion: Serialization) -> Return:
        target, (_, conversions) = conversion
        return self.visit_with_conversions(target, conversions)

    @staticmethod
    def _dataclass_fields_(
        fields: Sequence[Field], init_vars: Sequence[Field]
    ) -> Sequence[Field]:
        return fields

    @staticmethod
    def _field_conversions(
        field: Field, field_type: AnyType
    ) -> Tuple[AnyType, Optional[Conversions]]:
        conversions = get_field_conversions(field, field_type)
        if conversions is None:
            return field_type, None
        elif conversions.serializer is None:
            return field_type, conversions.serialization
        else:
            type_, *_ = conversions.serialization_conversion(field_type)
            return type_, conversions.serialization

    @staticmethod
    def _dependent_required(cls: Type) -> Requirements:
        return get_requiring(cls)[1]

    def _resolvers(self, cls: Type) -> Mapping[str, Resolver]:
        return get_resolvers(cls)
